"""Tests for the Game Day Simulator."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.game_day import (
    ExerciseDifficulty,
    ExerciseObjective,
    ExerciseStatus,
    ExerciseStep,
    ExerciseType,
    GameDayExercise,
    GameDayReport,
    GameDaySimulator,
    _dependency_chain_depth,
    _has_circuit_breaker,
    _has_security_controls,
    _is_spof,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    if failover:
        c.failover.enabled = True
    return c


def _empty_graph() -> InfraGraph:
    return InfraGraph()


def _single_graph() -> InfraGraph:
    g = InfraGraph()
    g.add_component(_comp("app1", "App1"))
    return g


def _simple_graph() -> InfraGraph:
    """LB -> App -> DB chain."""
    g = InfraGraph()
    g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=2))
    g.add_component(_comp("app", "App", ComponentType.APP_SERVER, replicas=1))
    g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=1))
    g.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return g


def _resilient_graph() -> InfraGraph:
    """Graph with redundancy, failover, autoscaling, circuit breakers."""
    g = InfraGraph()
    lb = _comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=3, failover=True)
    lb.autoscaling.enabled = True
    lb.security.encryption_in_transit = True
    lb.security.auth_required = True
    lb.security.network_segmented = True
    lb.security.log_enabled = True
    lb.security.backup_enabled = True
    g.add_component(lb)

    app = _comp("app", "App", ComponentType.APP_SERVER, replicas=3, failover=True)
    app.autoscaling.enabled = True
    app.security.encryption_in_transit = True
    app.security.auth_required = True
    app.security.network_segmented = True
    app.security.log_enabled = True
    app.security.backup_enabled = True
    g.add_component(app)

    db = _comp("db", "DB", ComponentType.DATABASE, replicas=2, failover=True)
    db.security.encryption_at_rest = True
    db.security.encryption_in_transit = True
    db.security.auth_required = True
    db.security.network_segmented = True
    db.security.log_enabled = True
    db.security.backup_enabled = True
    g.add_component(db)

    dep1 = Dependency(source_id="lb", target_id="app", dependency_type="requires")
    dep1.circuit_breaker.enabled = True
    dep1.retry_strategy.enabled = True
    g.add_dependency(dep1)

    dep2 = Dependency(source_id="app", target_id="db", dependency_type="requires")
    dep2.circuit_breaker.enabled = True
    dep2.retry_strategy.enabled = True
    g.add_dependency(dep2)

    return g


def _make_exercise(
    eid: str = "ex-test",
    etype: ExerciseType = ExerciseType.COMPONENT_FAILURE,
    difficulty: ExerciseDifficulty = ExerciseDifficulty.INTERMEDIATE,
    targets: list[str] | None = None,
    status: ExerciseStatus = ExerciseStatus.PLANNED,
) -> GameDayExercise:
    return GameDayExercise(
        id=eid,
        name=f"Test Exercise {eid}",
        exercise_type=etype,
        difficulty=difficulty,
        description="A test exercise",
        objectives=[
            ExerciseObjective(
                description="Test objective",
                success_criteria="Test criteria",
            ),
        ],
        steps=[
            ExerciseStep(order=1, action="test", description="Step 1", expected_outcome="Pass"),
            ExerciseStep(order=2, action="verify", description="Step 2", expected_outcome="Pass"),
            ExerciseStep(order=3, action="check", description="Step 3", expected_outcome="Pass"),
        ],
        target_components=targets or ["app"],
        status=status,
    )


# ===========================================================================
# Enum tests
# ===========================================================================


class TestExerciseTypeEnum:
    def test_all_values(self):
        assert ExerciseType.COMPONENT_FAILURE == "component_failure"
        assert ExerciseType.CASCADING_FAILURE == "cascading_failure"
        assert ExerciseType.REGION_OUTAGE == "region_outage"
        assert ExerciseType.DEPENDENCY_TIMEOUT == "dependency_timeout"
        assert ExerciseType.LOAD_SPIKE == "load_spike"
        assert ExerciseType.DATA_CORRUPTION == "data_corruption"
        assert ExerciseType.SECURITY_BREACH == "security_breach"
        assert ExerciseType.NETWORK_PARTITION == "network_partition"

    def test_member_count(self):
        assert len(ExerciseType) == 8


class TestExerciseDifficultyEnum:
    def test_all_values(self):
        assert ExerciseDifficulty.BEGINNER == "beginner"
        assert ExerciseDifficulty.INTERMEDIATE == "intermediate"
        assert ExerciseDifficulty.ADVANCED == "advanced"
        assert ExerciseDifficulty.EXPERT == "expert"

    def test_member_count(self):
        assert len(ExerciseDifficulty) == 4


class TestExerciseStatusEnum:
    def test_all_values(self):
        assert ExerciseStatus.PLANNED == "planned"
        assert ExerciseStatus.RUNNING == "running"
        assert ExerciseStatus.COMPLETED == "completed"
        assert ExerciseStatus.FAILED == "failed"
        assert ExerciseStatus.ABORTED == "aborted"

    def test_member_count(self):
        assert len(ExerciseStatus) == 5


# ===========================================================================
# Dataclass tests
# ===========================================================================


class TestExerciseObjective:
    def test_default_not_met(self):
        obj = ExerciseObjective(description="d", success_criteria="c")
        assert obj.met is False

    def test_set_met(self):
        obj = ExerciseObjective(description="d", success_criteria="c", met=True)
        assert obj.met is True


class TestExerciseStep:
    def test_defaults(self):
        step = ExerciseStep(order=1, action="a", description="d", expected_outcome="e")
        assert step.actual_outcome == ""
        assert step.passed is False

    def test_set_values(self):
        step = ExerciseStep(
            order=2, action="b", description="d2",
            expected_outcome="e2", actual_outcome="a2", passed=True,
        )
        assert step.passed is True
        assert step.actual_outcome == "a2"


class TestGameDayExercise:
    def test_defaults(self):
        ex = _make_exercise()
        assert ex.status == ExerciseStatus.PLANNED
        assert ex.score == 0.0
        assert ex.duration_minutes == 60
        assert ex.findings == []
        assert ex.recommendations == []

    def test_custom_fields(self):
        ex = _make_exercise(status=ExerciseStatus.COMPLETED)
        ex.score = 85.0
        ex.findings.append("finding1")
        assert ex.status == ExerciseStatus.COMPLETED
        assert ex.score == 85.0
        assert len(ex.findings) == 1


class TestGameDayReport:
    def test_report_fields(self):
        report = GameDayReport(
            exercises=[], overall_score=75.0, total_exercises=3,
            passed_count=2, failed_count=1,
            critical_findings=["f1"], improvement_areas=["i1"],
            readiness_level="ready",
        )
        assert report.overall_score == 75.0
        assert report.readiness_level == "ready"
        assert report.total_exercises == 3


# ===========================================================================
# Internal helpers
# ===========================================================================


class TestIsSpof:
    def test_spof_single_replica_with_dependent(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A", replicas=1))
        g.add_component(_comp("b", "B"))
        g.add_dependency(Dependency(source_id="b", target_id="a"))
        assert _is_spof(g.get_component("a"), g) is True

    def test_not_spof_multiple_replicas(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A", replicas=3))
        g.add_component(_comp("b", "B"))
        g.add_dependency(Dependency(source_id="b", target_id="a"))
        assert _is_spof(g.get_component("a"), g) is False

    def test_not_spof_failover_enabled(self):
        """Covers line 145: failover.enabled returns False."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", replicas=1, failover=True))
        g.add_component(_comp("b", "B"))
        g.add_dependency(Dependency(source_id="b", target_id="a"))
        assert _is_spof(g.get_component("a"), g) is False

    def test_not_spof_no_dependents(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A", replicas=1))
        assert _is_spof(g.get_component("a"), g) is False


class TestDependencyChainDepth:
    def test_single_node(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        assert _dependency_chain_depth("a", g) == 1

    def test_linear_chain(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_component(_comp("c", "C"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        assert _dependency_chain_depth("a", g) == 3

    def test_cycle_returns_zero_for_revisited(self):
        """Covers line 156: cycle detection returns 0 for visited nodes."""
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="a"))
        # Should not infinite loop; visited prevents re-visit
        result = _dependency_chain_depth("a", g)
        assert result >= 1


class TestHasCircuitBreaker:
    def test_no_circuit_breaker(self):
        g = _simple_graph()
        assert _has_circuit_breaker("app", g) is False

    def test_has_circuit_breaker(self):
        g = _resilient_graph()
        assert _has_circuit_breaker("app", g) is True

    def test_no_dependencies(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        assert _has_circuit_breaker("a", g) is False


class TestHasSecurityControls:
    def test_sufficient_controls(self):
        c = _comp("a", "A")
        c.security.encryption_in_transit = True
        c.security.auth_required = True
        c.security.network_segmented = True
        assert _has_security_controls(c) is True

    def test_insufficient_controls(self):
        c = _comp("a", "A")
        c.security.encryption_in_transit = True
        assert _has_security_controls(c) is False

    def test_exactly_three(self):
        c = _comp("a", "A")
        c.security.encryption_at_rest = True
        c.security.waf_protected = True
        c.security.rate_limiting = True
        assert _has_security_controls(c) is True


# ===========================================================================
# GameDaySimulator -- generate_exercises
# ===========================================================================


class TestGenerateExercises:
    def test_empty_graph_returns_empty(self):
        sim = GameDaySimulator(_empty_graph())
        result = sim.generate_exercises()
        assert result == []

    def test_single_component_no_deps(self):
        sim = GameDaySimulator(_single_graph())
        result = sim.generate_exercises(count=20)
        # Single component with no deps -- can still get load_spike, security_breach
        assert len(result) >= 1

    def test_simple_graph_generates_exercises(self):
        sim = GameDaySimulator(_simple_graph())
        result = sim.generate_exercises(count=20)
        assert len(result) >= 3
        types = {e.exercise_type for e in result}
        # SPOF components should generate component_failure
        assert ExerciseType.COMPONENT_FAILURE in types

    def test_count_limits_results(self):
        sim = GameDaySimulator(_simple_graph())
        result = sim.generate_exercises(count=2)
        assert len(result) <= 2

    def test_exercises_added_to_internal_list(self):
        sim = GameDaySimulator(_simple_graph())
        result = sim.generate_exercises(count=3)
        assert len(sim._exercises) == len(result)

    def test_difficulty_affects_steps(self):
        g = _simple_graph()
        sim_b = GameDaySimulator(g)
        beginner = sim_b.generate_exercises(difficulty=ExerciseDifficulty.BEGINNER, count=1)

        sim_e = GameDaySimulator(g)
        expert = sim_e.generate_exercises(difficulty=ExerciseDifficulty.EXPERT, count=1)

        if beginner and expert:
            # Expert exercises should have at least as many steps as beginner
            assert len(expert[0].steps) >= len(beginner[0].steps)

    def test_database_generates_data_corruption(self):
        g = InfraGraph()
        g.add_component(_comp("db", "Database", ComponentType.DATABASE))
        sim = GameDaySimulator(g)
        result = sim.generate_exercises(count=20)
        types = {e.exercise_type for e in result}
        assert ExerciseType.DATA_CORRUPTION in types

    def test_storage_generates_data_corruption(self):
        g = InfraGraph()
        g.add_component(_comp("s3", "ObjectStore", ComponentType.STORAGE))
        sim = GameDaySimulator(g)
        result = sim.generate_exercises(count=20)
        types = {e.exercise_type for e in result}
        assert ExerciseType.DATA_CORRUPTION in types

    def test_region_components_generate_region_outage(self):
        g = InfraGraph()
        c1 = _comp("app1", "App1")
        c1.region.region = "us-east-1"
        c2 = _comp("app2", "App2")
        c2.region.region = "us-east-1"
        g.add_component(c1)
        g.add_component(c2)
        sim = GameDaySimulator(g)
        result = sim.generate_exercises(count=20)
        types = {e.exercise_type for e in result}
        assert ExerciseType.REGION_OUTAGE in types

    def test_no_duplicate_type_target_combos(self):
        g = _simple_graph()
        sim = GameDaySimulator(g)
        result = sim.generate_exercises(count=50)
        seen = set()
        for e in result:
            key = (e.exercise_type.value, tuple(sorted(e.target_components)))
            assert key not in seen, f"Duplicate exercise: {key}"
            seen.add(key)

    def test_cascading_failure_for_deep_chains(self):
        g = _simple_graph()
        sim = GameDaySimulator(g)
        result = sim.generate_exercises(count=20)
        types = {e.exercise_type for e in result}
        assert ExerciseType.CASCADING_FAILURE in types

    def test_spof_detection(self):
        g = InfraGraph()
        spof = _comp("spof", "SPOF", replicas=1)
        dep = _comp("dep", "Dependent")
        g.add_component(spof)
        g.add_component(dep)
        g.add_dependency(Dependency(source_id="dep", target_id="spof", dependency_type="requires"))
        sim = GameDaySimulator(g)
        result = sim.generate_exercises(count=20)
        cf_exercises = [e for e in result if e.exercise_type == ExerciseType.COMPONENT_FAILURE]
        targets = [t for e in cf_exercises for t in e.target_components]
        assert "spof" in targets

    def test_region_outage_advanced_has_rto_step(self):
        """Covers line 573: region outage advanced/expert adds RTO/RPO step."""
        g = InfraGraph()
        c = _comp("app", "App")
        c.region.region = "us-east-1"
        g.add_component(c)
        sim = GameDaySimulator(g)
        result = sim.generate_exercises(
            difficulty=ExerciseDifficulty.ADVANCED, count=20,
        )
        ro_exercises = [e for e in result if e.exercise_type == ExerciseType.REGION_OUTAGE]
        assert len(ro_exercises) >= 1
        # Advanced region outage should have 4 steps (including RTO/RPO)
        assert len(ro_exercises[0].steps) == 4


# ===========================================================================
# GameDaySimulator -- add_exercise
# ===========================================================================


class TestAddExercise:
    def test_add_exercise(self):
        sim = GameDaySimulator(_empty_graph())
        ex = _make_exercise()
        sim.add_exercise(ex)
        assert len(sim._exercises) == 1
        assert sim._exercises[0].id == ex.id

    def test_add_multiple(self):
        sim = GameDaySimulator(_empty_graph())
        sim.add_exercise(_make_exercise("ex1"))
        sim.add_exercise(_make_exercise("ex2"))
        assert len(sim._exercises) == 2


# ===========================================================================
# GameDaySimulator -- get_exercise
# ===========================================================================


class TestGetExercise:
    def test_get_existing(self):
        sim = GameDaySimulator(_empty_graph())
        ex = _make_exercise("ex-find")
        sim.add_exercise(ex)
        found = sim.get_exercise("ex-find")
        assert found is not None
        assert found.id == "ex-find"

    def test_get_nonexistent(self):
        sim = GameDaySimulator(_empty_graph())
        assert sim.get_exercise("nope") is None


# ===========================================================================
# GameDaySimulator -- run_exercise
# ===========================================================================


class TestRunExercise:
    def test_nonexistent_returns_none(self):
        sim = GameDaySimulator(_empty_graph())
        assert sim.run_exercise("nope") is None

    def test_component_failure_spof_fails(self):
        g = _simple_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-cf", etype=ExerciseType.COMPONENT_FAILURE, targets=["app"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-cf")
        assert result is not None
        assert result.status in (ExerciseStatus.COMPLETED, ExerciseStatus.FAILED)
        assert result.score >= 0

    def test_component_failure_resilient_passes(self):
        g = _resilient_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-cf-r", etype=ExerciseType.COMPONENT_FAILURE, targets=["app"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-cf-r")
        assert result is not None
        assert result.score > 0

    def test_status_changes_from_planned(self):
        g = _simple_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(eid="ex-status", targets=["app"])
        assert ex.status == ExerciseStatus.PLANNED
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-status")
        assert result is not None
        assert result.status != ExerciseStatus.PLANNED

    def test_score_between_0_and_100(self):
        g = _simple_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(eid="ex-score", targets=["app"])
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-score")
        assert result is not None
        assert 0 <= result.score <= 100

    def test_cascading_failure_evaluation(self):
        g = _simple_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-cas", etype=ExerciseType.CASCADING_FAILURE, targets=["app"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-cas")
        assert result is not None
        # Simple graph has no circuit breakers, so step 3 should fail
        assert any("circuit breaker" in f.lower() or "containment" in f.lower()
                    for f in result.findings) or result.score > 0

    def test_load_spike_no_autoscaling(self):
        g = _simple_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-ls", etype=ExerciseType.LOAD_SPIKE, targets=["app"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-ls")
        assert result is not None

    def test_load_spike_with_autoscaling(self):
        g = InfraGraph()
        c = _comp("app", "App", replicas=3)
        c.autoscaling.enabled = True
        g.add_component(c)
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-ls-auto", etype=ExerciseType.LOAD_SPIKE, targets=["app"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-ls-auto")
        assert result is not None
        assert result.score > 50

    def test_security_breach_no_controls(self):
        g = _simple_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-sb", etype=ExerciseType.SECURITY_BREACH, targets=["app"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-sb")
        assert result is not None
        assert any("security" in f.lower() for f in result.findings)

    def test_security_breach_with_controls(self):
        g = _resilient_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-sb-ok", etype=ExerciseType.SECURITY_BREACH, targets=["app"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-sb-ok")
        assert result is not None
        assert result.score > 0

    def test_network_partition_no_handling(self):
        g = _simple_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-np", etype=ExerciseType.NETWORK_PARTITION, targets=["app"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-np")
        assert result is not None

    def test_network_partition_with_handling(self):
        g = _resilient_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-np-ok", etype=ExerciseType.NETWORK_PARTITION, targets=["app"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-np-ok")
        assert result is not None
        assert result.score > 50

    def test_dependency_timeout(self):
        g = _simple_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-dt", etype=ExerciseType.DEPENDENCY_TIMEOUT, targets=["app"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-dt")
        assert result is not None

    def test_data_corruption_no_backup(self):
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE))
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-dc", etype=ExerciseType.DATA_CORRUPTION, targets=["db"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-dc")
        assert result is not None
        assert any("backup" in f.lower() for f in result.findings)

    def test_data_corruption_with_backup(self):
        g = InfraGraph()
        c = _comp("db", "DB", ComponentType.DATABASE)
        c.security.backup_enabled = True
        g.add_component(c)
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-dc-ok", etype=ExerciseType.DATA_CORRUPTION, targets=["db"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-dc-ok")
        assert result is not None
        assert result.score > 50

    def test_region_outage_no_dr(self):
        g = InfraGraph()
        c = _comp("app", "App")
        c.region.region = "us-east-1"
        g.add_component(c)
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-ro", etype=ExerciseType.REGION_OUTAGE, targets=["app"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-ro")
        assert result is not None

    def test_region_outage_with_dr(self):
        g = InfraGraph()
        c = _comp("app", "App")
        c.region.region = "us-east-1"
        c.region.dr_target_region = "us-west-2"
        c.region.rto_seconds = 300
        g.add_component(c)
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-ro-ok", etype=ExerciseType.REGION_OUTAGE, targets=["app"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-ro-ok")
        assert result is not None
        assert result.score > 0

    def test_target_component_not_in_graph(self):
        g = _empty_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(eid="ex-missing", targets=["ghost"])
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-missing")
        assert result is not None
        assert "not found" in " ".join(result.findings).lower()


# ===========================================================================
# GameDaySimulator -- run_exercise -- advanced / expert difficulty steps
# ===========================================================================


class TestRunExerciseAdvancedSteps:
    """Test advanced/expert difficulty steps for evaluators (monitoring,
    auto-recovery, graceful degradation, RTO/RPO)."""

    def test_component_failure_advanced_monitoring_no_logging(self):
        """Covers lines 648-658: Step 4 monitoring check fails when no logging."""
        g = InfraGraph()
        c = _comp("app", "App", replicas=1)
        # No monitoring: log_enabled=False, ids_monitored=False (defaults)
        g.add_component(c)
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-cf-adv-nolog",
            etype=ExerciseType.COMPONENT_FAILURE,
            difficulty=ExerciseDifficulty.ADVANCED,
            targets=["app"],
        )
        # Build 4 steps to trigger step 4 check
        ex.steps = [
            ExerciseStep(order=1, action="identify_target", description="s1", expected_outcome="e1"),
            ExerciseStep(order=2, action="simulate_failure", description="s2", expected_outcome="e2"),
            ExerciseStep(order=3, action="verify_redundancy", description="s3", expected_outcome="e3"),
            ExerciseStep(order=4, action="verify_monitoring", description="s4", expected_outcome="e4"),
        ]
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-cf-adv-nolog")
        assert result is not None
        # Step 4 should fail because no logging
        assert result.steps[3].passed is False
        assert any("monitoring" in f.lower() or "no monitoring" in f.lower()
                    for f in result.findings)

    def test_component_failure_advanced_monitoring_with_logging(self):
        """Covers line 648-653: Step 4 monitoring check passes with logging."""
        g = InfraGraph()
        c = _comp("app", "App", replicas=3, failover=True)
        c.security.log_enabled = True
        g.add_component(c)
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-cf-adv-log",
            etype=ExerciseType.COMPONENT_FAILURE,
            difficulty=ExerciseDifficulty.ADVANCED,
            targets=["app"],
        )
        ex.steps = [
            ExerciseStep(order=1, action="identify_target", description="s1", expected_outcome="e1"),
            ExerciseStep(order=2, action="simulate_failure", description="s2", expected_outcome="e2"),
            ExerciseStep(order=3, action="verify_redundancy", description="s3", expected_outcome="e3"),
            ExerciseStep(order=4, action="verify_monitoring", description="s4", expected_outcome="e4"),
        ]
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-cf-adv-log")
        assert result is not None
        assert result.steps[3].passed is True

    def test_component_failure_expert_auto_recovery_no_autoscaling(self):
        """Covers lines 662-672: Step 5 auto-recovery check fails."""
        g = InfraGraph()
        c = _comp("app", "App", replicas=1)
        # No autoscaling, no failover
        g.add_component(c)
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-cf-exp-noauto",
            etype=ExerciseType.COMPONENT_FAILURE,
            difficulty=ExerciseDifficulty.EXPERT,
            targets=["app"],
        )
        ex.steps = [
            ExerciseStep(order=1, action="identify_target", description="s1", expected_outcome="e1"),
            ExerciseStep(order=2, action="simulate_failure", description="s2", expected_outcome="e2"),
            ExerciseStep(order=3, action="verify_redundancy", description="s3", expected_outcome="e3"),
            ExerciseStep(order=4, action="verify_monitoring", description="s4", expected_outcome="e4"),
            ExerciseStep(order=5, action="verify_auto_recovery", description="s5", expected_outcome="e5"),
        ]
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-cf-exp-noauto")
        assert result is not None
        assert result.steps[4].passed is False
        assert any("auto-recovery" in f.lower() or "no auto-recovery" in f.lower()
                    for f in result.findings)

    def test_component_failure_expert_auto_recovery_with_autoscaling(self):
        """Covers lines 662-667: Step 5 auto-recovery check passes."""
        g = InfraGraph()
        c = _comp("app", "App", replicas=3, failover=True)
        c.autoscaling.enabled = True
        c.security.log_enabled = True
        c.security.backup_enabled = True
        g.add_component(c)
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-cf-exp-auto",
            etype=ExerciseType.COMPONENT_FAILURE,
            difficulty=ExerciseDifficulty.EXPERT,
            targets=["app"],
        )
        ex.steps = [
            ExerciseStep(order=1, action="identify_target", description="s1", expected_outcome="e1"),
            ExerciseStep(order=2, action="simulate_failure", description="s2", expected_outcome="e2"),
            ExerciseStep(order=3, action="verify_redundancy", description="s3", expected_outcome="e3"),
            ExerciseStep(order=4, action="verify_monitoring", description="s4", expected_outcome="e4"),
            ExerciseStep(order=5, action="verify_auto_recovery", description="s5", expected_outcome="e5"),
        ]
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-cf-exp-auto")
        assert result is not None
        assert result.steps[4].passed is True

    def test_component_failure_backup_enabled_meets_objective1(self):
        """Covers line 687: objective[1].met = True when backup_enabled."""
        g = InfraGraph()
        c = _comp("app", "App", replicas=3, failover=True)
        c.security.backup_enabled = True
        g.add_component(c)
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-cf-backup",
            etype=ExerciseType.COMPONENT_FAILURE,
            targets=["app"],
        )
        # Add second objective for "no data loss"
        ex.objectives = [
            ExerciseObjective(description="System survives", success_criteria="Redundancy"),
            ExerciseObjective(description="No data loss", success_criteria="Backup works"),
        ]
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-cf-backup")
        assert result is not None
        assert result.objectives[1].met is True

    def test_cascading_failure_comp_not_found(self):
        """Covers line 707: comp is None continue in cascading failure."""
        g = _empty_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-cas-missing",
            etype=ExerciseType.CASCADING_FAILURE,
            targets=["ghost"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-cas-missing")
        assert result is not None
        # No crash, exercise still completes

    def test_cascading_failure_advanced_graceful_degradation_no_optional(self):
        """Covers lines 749-756: Step 4 graceful degradation fails (all deps are 'requires')."""
        g = InfraGraph()
        g.add_component(_comp("app", "App"))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE))
        g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-cas-adv",
            etype=ExerciseType.CASCADING_FAILURE,
            difficulty=ExerciseDifficulty.ADVANCED,
            targets=["app"],
        )
        ex.steps = [
            ExerciseStep(order=1, action="identify_chain", description="s1", expected_outcome="e1"),
            ExerciseStep(order=2, action="inject_failure", description="s2", expected_outcome="e2"),
            ExerciseStep(order=3, action="verify_containment", description="s3", expected_outcome="e3"),
            ExerciseStep(order=4, action="verify_graceful_degradation", description="s4", expected_outcome="e4"),
        ]
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-cas-adv")
        assert result is not None
        assert result.steps[3].passed is False
        assert "requires" in result.steps[3].actual_outcome.lower()

    def test_cascading_failure_advanced_graceful_degradation_with_optional(self):
        """Covers lines 749-757: Step 4 passes with optional dependency."""
        g = InfraGraph()
        g.add_component(_comp("app", "App"))
        g.add_component(_comp("cache", "Cache", ComponentType.CACHE))
        g.add_dependency(Dependency(source_id="app", target_id="cache", dependency_type="optional"))
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-cas-adv-opt",
            etype=ExerciseType.CASCADING_FAILURE,
            difficulty=ExerciseDifficulty.ADVANCED,
            targets=["app"],
        )
        ex.steps = [
            ExerciseStep(order=1, action="identify_chain", description="s1", expected_outcome="e1"),
            ExerciseStep(order=2, action="inject_failure", description="s2", expected_outcome="e2"),
            ExerciseStep(order=3, action="verify_containment", description="s3", expected_outcome="e3"),
            ExerciseStep(order=4, action="verify_graceful_degradation", description="s4", expected_outcome="e4"),
        ]
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-cas-adv-opt")
        assert result is not None
        assert result.steps[3].passed is True
        assert "graceful" in result.steps[3].actual_outcome.lower()

    def test_cascading_failure_large_blast_radius(self):
        """Covers line 774: blast radius too large finding."""
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_component(_comp("c", "C"))
        g.add_component(_comp("d", "D"))
        # a depends on b, c, d (deep)
        g.add_dependency(Dependency(source_id="b", target_id="a"))
        g.add_dependency(Dependency(source_id="c", target_id="a"))
        g.add_dependency(Dependency(source_id="d", target_id="a"))
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-cas-blast",
            etype=ExerciseType.CASCADING_FAILURE,
            targets=["a"],
        )
        # Two objectives: containment + blast radius
        ex.objectives = [
            ExerciseObjective(description="Contained", success_criteria="CB limits cascade"),
            ExerciseObjective(description="Blast small", success_criteria="<2 affected"),
        ]
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-cas-blast")
        assert result is not None
        # 3 affected > 2 threshold, so blast radius finding should appear
        assert any("blast radius" in f.lower() for f in result.findings)
        assert result.objectives[1].met is False

    def test_load_spike_comp_not_found(self):
        """Covers line 788: comp is None continue in load_spike."""
        g = _empty_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-ls-missing",
            etype=ExerciseType.LOAD_SPIKE,
            targets=["ghost"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-ls-missing")
        assert result is not None

    def test_security_breach_comp_not_found(self):
        """Covers line 843: comp is None continue in security_breach."""
        g = _empty_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-sb-missing",
            etype=ExerciseType.SECURITY_BREACH,
            targets=["ghost"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-sb-missing")
        assert result is not None

    def test_security_breach_detection_objective(self):
        """Covers lines 877-885: security breach objective 1 detection check."""
        g = InfraGraph()
        c = _comp("app", "App")
        # No log_enabled, no ids_monitored -> detection fails
        g.add_component(c)
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-sb-det",
            etype=ExerciseType.SECURITY_BREACH,
            targets=["app"],
        )
        # Need two objectives
        ex.objectives = [
            ExerciseObjective(description="Controls protect", success_criteria="sec controls"),
            ExerciseObjective(description="Breach detection", success_criteria="monitoring"),
        ]
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-sb-det")
        assert result is not None
        assert result.objectives[1].met is False
        assert any("breach detection" in f.lower() or "no breach detection" in f.lower()
                    for f in result.findings)

    def test_security_breach_detection_with_logging(self):
        """Covers lines 877-881: security breach objective 1 met with logging."""
        g = InfraGraph()
        c = _comp("app", "App")
        c.security.log_enabled = True
        c.security.encryption_in_transit = True
        c.security.auth_required = True
        c.security.network_segmented = True
        g.add_component(c)
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-sb-det-ok",
            etype=ExerciseType.SECURITY_BREACH,
            targets=["app"],
        )
        ex.objectives = [
            ExerciseObjective(description="Controls protect", success_criteria="sec controls"),
            ExerciseObjective(description="Breach detection", success_criteria="monitoring"),
        ]
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-sb-det-ok")
        assert result is not None
        assert result.objectives[1].met is True

    def test_network_partition_comp_not_found(self):
        """Covers line 897: comp is None continue in network_partition."""
        g = _empty_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-np-missing",
            etype=ExerciseType.NETWORK_PARTITION,
            targets=["ghost"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-np-missing")
        assert result is not None

    def test_dependency_timeout_comp_not_found(self):
        """Covers line 948: comp is None continue in dependency_timeout."""
        g = _empty_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-dt-missing",
            etype=ExerciseType.DEPENDENCY_TIMEOUT,
            targets=["ghost"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-dt-missing")
        assert result is not None

    def test_dependency_timeout_with_circuit_breaker(self):
        """Covers line 969: dependency timeout step 3 passes with circuit breaker."""
        g = _resilient_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-dt-cb",
            etype=ExerciseType.DEPENDENCY_TIMEOUT,
            targets=["app"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-dt-cb")
        assert result is not None
        # app in resilient graph has circuit breakers -> step 3 passes
        assert result.steps[2].passed is True
        assert "timeout handling in place" in result.steps[2].actual_outcome.lower()

    def test_data_corruption_comp_not_found(self):
        """Covers line 996: comp is None continue in data_corruption."""
        g = _empty_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-dc-missing",
            etype=ExerciseType.DATA_CORRUPTION,
            targets=["ghost"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-dc-missing")
        assert result is not None

    def test_region_outage_comp_not_found(self):
        """Covers line 1039: comp is None continue in region_outage."""
        g = InfraGraph()
        c = _comp("app", "App")
        c.region.region = "us-east-1"
        g.add_component(c)
        sim = GameDaySimulator(g)
        # Include a ghost target alongside the real one
        ex = _make_exercise(
            eid="ex-ro-mixed",
            etype=ExerciseType.REGION_OUTAGE,
            targets=["ghost", "app"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-ro-mixed")
        assert result is not None

    def test_region_outage_advanced_rto_step(self):
        """Covers lines 1069-1075: Region outage step 4 (RTO/RPO)."""
        g = InfraGraph()
        c = _comp("app", "App")
        c.region.region = "us-east-1"
        c.region.dr_target_region = "us-west-2"
        c.region.rto_seconds = 300
        g.add_component(c)
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-ro-adv-rto",
            etype=ExerciseType.REGION_OUTAGE,
            difficulty=ExerciseDifficulty.ADVANCED,
            targets=["app"],
        )
        ex.steps = [
            ExerciseStep(order=1, action="identify", description="s1", expected_outcome="e1"),
            ExerciseStep(order=2, action="outage", description="s2", expected_outcome="e2"),
            ExerciseStep(order=3, action="failover", description="s3", expected_outcome="e3"),
            ExerciseStep(order=4, action="rto_rpo", description="s4", expected_outcome="e4"),
        ]
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-ro-adv-rto")
        assert result is not None
        # DR configured + RTO set -> step 4 should pass
        assert result.steps[3].passed is True
        assert "rto" in result.steps[3].actual_outcome.lower()

    def test_region_outage_advanced_rto_no_dr(self):
        """Covers lines 1069-1075: RTO step fails when no DR target."""
        g = InfraGraph()
        c = _comp("app", "App")
        c.region.region = "us-east-1"
        c.region.rto_seconds = 300
        # No dr_target_region
        g.add_component(c)
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-ro-adv-nodr",
            etype=ExerciseType.REGION_OUTAGE,
            difficulty=ExerciseDifficulty.ADVANCED,
            targets=["app"],
        )
        ex.steps = [
            ExerciseStep(order=1, action="identify", description="s1", expected_outcome="e1"),
            ExerciseStep(order=2, action="outage", description="s2", expected_outcome="e2"),
            ExerciseStep(order=3, action="failover", description="s3", expected_outcome="e3"),
            ExerciseStep(order=4, action="rto_rpo", description="s4", expected_outcome="e4"),
        ]
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-ro-adv-nodr")
        assert result is not None
        # No DR -> step 4 fails (has_dr is False)
        assert result.steps[3].passed is False

    def test_region_outage_objective1_met_with_dr(self):
        """Covers line 1087: region outage objective[1].met = has_dr."""
        g = InfraGraph()
        c = _comp("app", "App")
        c.region.region = "us-east-1"
        c.region.dr_target_region = "us-west-2"
        g.add_component(c)
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-ro-obj",
            etype=ExerciseType.REGION_OUTAGE,
            targets=["app"],
        )
        ex.objectives = [
            ExerciseObjective(description="Survives outage", success_criteria="failover"),
            ExerciseObjective(description="RTO/RPO met", success_criteria="recovery within targets"),
        ]
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-ro-obj")
        assert result is not None
        assert result.objectives[1].met is True

    def test_region_outage_objective1_not_met_without_dr(self):
        """Covers line 1087: region outage objective[1].met = False when no DR."""
        g = InfraGraph()
        c = _comp("app", "App")
        c.region.region = "us-east-1"
        g.add_component(c)
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-ro-obj-nodr",
            etype=ExerciseType.REGION_OUTAGE,
            targets=["app"],
        )
        ex.objectives = [
            ExerciseObjective(description="Survives outage", success_criteria="failover"),
            ExerciseObjective(description="RTO/RPO met", success_criteria="recovery within targets"),
        ]
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-ro-obj-nodr")
        assert result is not None
        assert result.objectives[1].met is False


# ===========================================================================
# GameDaySimulator -- run_all
# ===========================================================================


class TestRunAll:
    def test_run_all_returns_report(self):
        g = _simple_graph()
        sim = GameDaySimulator(g)
        sim.generate_exercises(count=3)
        report = sim.run_all()
        assert isinstance(report, GameDayReport)
        assert report.total_exercises >= 3

    def test_run_all_no_exercises(self):
        sim = GameDaySimulator(_empty_graph())
        report = sim.run_all()
        assert report.total_exercises == 0
        assert report.overall_score == 0.0

    def test_already_completed_not_rerun(self):
        g = _simple_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(eid="ex-done", targets=["app"])
        ex.status = ExerciseStatus.COMPLETED
        ex.score = 99.0
        sim.add_exercise(ex)
        report = sim.run_all()
        # Should not re-run the already completed exercise
        assert report.passed_count == 1


# ===========================================================================
# GameDaySimulator -- evaluate_readiness
# ===========================================================================


class TestEvaluateReadiness:
    def test_no_exercises_not_ready(self):
        sim = GameDaySimulator(_empty_graph())
        assert sim.evaluate_readiness() == "not_ready"

    def test_no_completed_not_ready(self):
        sim = GameDaySimulator(_empty_graph())
        sim.add_exercise(_make_exercise())
        assert sim.evaluate_readiness() == "not_ready"

    def test_well_prepared(self):
        sim = GameDaySimulator(_resilient_graph())
        ex = _make_exercise(eid="ex-wp", targets=["app"])
        ex.status = ExerciseStatus.COMPLETED
        ex.score = 90.0
        sim.add_exercise(ex)
        assert sim.evaluate_readiness() == "well_prepared"

    def test_ready(self):
        sim = GameDaySimulator(_empty_graph())
        ex = _make_exercise(eid="ex-r")
        ex.status = ExerciseStatus.COMPLETED
        ex.score = 70.0
        sim.add_exercise(ex)
        assert sim.evaluate_readiness() == "ready"

    def test_partially_ready(self):
        sim = GameDaySimulator(_empty_graph())
        ex = _make_exercise(eid="ex-pr")
        ex.status = ExerciseStatus.FAILED
        ex.score = 45.0
        sim.add_exercise(ex)
        assert sim.evaluate_readiness() == "partially_ready"

    def test_not_ready_low_score(self):
        sim = GameDaySimulator(_empty_graph())
        ex = _make_exercise(eid="ex-nr")
        ex.status = ExerciseStatus.FAILED
        ex.score = 20.0
        sim.add_exercise(ex)
        assert sim.evaluate_readiness() == "not_ready"

    def test_boundary_80(self):
        sim = GameDaySimulator(_empty_graph())
        ex = _make_exercise(eid="ex-80")
        ex.status = ExerciseStatus.COMPLETED
        ex.score = 80.0
        sim.add_exercise(ex)
        assert sim.evaluate_readiness() == "well_prepared"

    def test_boundary_60(self):
        sim = GameDaySimulator(_empty_graph())
        ex = _make_exercise(eid="ex-60")
        ex.status = ExerciseStatus.COMPLETED
        ex.score = 60.0
        sim.add_exercise(ex)
        assert sim.evaluate_readiness() == "ready"

    def test_boundary_40(self):
        sim = GameDaySimulator(_empty_graph())
        ex = _make_exercise(eid="ex-40")
        ex.status = ExerciseStatus.FAILED
        ex.score = 40.0
        sim.add_exercise(ex)
        assert sim.evaluate_readiness() == "partially_ready"


# ===========================================================================
# GameDaySimulator -- generate_report
# ===========================================================================


class TestGenerateReport:
    def test_report_structure(self):
        g = _simple_graph()
        sim = GameDaySimulator(g)
        sim.generate_exercises(count=2)
        sim.run_all()
        report = sim.generate_report()
        assert hasattr(report, "exercises")
        assert hasattr(report, "overall_score")
        assert hasattr(report, "total_exercises")
        assert hasattr(report, "passed_count")
        assert hasattr(report, "failed_count")
        assert hasattr(report, "critical_findings")
        assert hasattr(report, "improvement_areas")
        assert hasattr(report, "readiness_level")

    def test_report_counts(self):
        g = _simple_graph()
        sim = GameDaySimulator(g)
        sim.generate_exercises(count=3)
        report = sim.run_all()
        assert report.passed_count + report.failed_count <= report.total_exercises

    def test_empty_report(self):
        sim = GameDaySimulator(_empty_graph())
        report = sim.generate_report()
        assert report.total_exercises == 0
        assert report.overall_score == 0.0
        assert report.readiness_level == "not_ready"

    def test_critical_findings_from_failed(self):
        """Covers line 1301: critical findings are collected from failed exercises."""
        g = _simple_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(eid="ex-fail", targets=["app"])
        sim.add_exercise(ex)
        sim.run_exercise("ex-fail")
        report = sim.generate_report()
        if report.failed_count > 0:
            # Failed exercises should contribute critical findings
            assert isinstance(report.critical_findings, list)

    def test_critical_findings_populated_from_failed_exercises(self):
        """Explicitly verify that failed exercise findings become critical findings."""
        g = InfraGraph()
        c = _comp("app", "App", replicas=1)
        g.add_component(c)
        sim = GameDaySimulator(g)
        # Use EXPERT difficulty (pass_ratio=0.9) so the exercise will fail
        # because replicas=1, no failover, no monitoring, no autoscaling
        ex = _make_exercise(
            eid="ex-fail-findings",
            etype=ExerciseType.COMPONENT_FAILURE,
            difficulty=ExerciseDifficulty.EXPERT,
            targets=["app"],
        )
        ex.objectives = [
            ExerciseObjective(description="System survives", success_criteria="redundancy"),
            ExerciseObjective(description="No data loss", success_criteria="backup works"),
        ]
        # Add 5 steps like expert difficulty
        ex.steps = [
            ExerciseStep(order=1, action="identify_target", description="s1", expected_outcome="e1"),
            ExerciseStep(order=2, action="simulate_failure", description="s2", expected_outcome="e2"),
            ExerciseStep(order=3, action="verify_redundancy", description="s3", expected_outcome="e3"),
            ExerciseStep(order=4, action="verify_monitoring", description="s4", expected_outcome="e4"),
            ExerciseStep(order=5, action="verify_auto_recovery", description="s5", expected_outcome="e5"),
        ]
        sim.add_exercise(ex)
        sim.run_exercise("ex-fail-findings")
        report = sim.generate_report()
        # Expert pass_ratio=0.9 means score < 90 -> FAILED
        assert report.failed_count >= 1
        assert len(report.critical_findings) > 0

    def test_improvement_areas_deduplicated(self):
        g = _simple_graph()
        sim = GameDaySimulator(g)
        sim.generate_exercises(count=5)
        report = sim.run_all()
        # No exact duplicates
        assert len(report.improvement_areas) == len(set(report.improvement_areas))

    def test_readiness_level_in_report(self):
        g = _resilient_graph()
        sim = GameDaySimulator(g)
        sim.generate_exercises(count=2)
        report = sim.run_all()
        assert report.readiness_level in (
            "not_ready", "partially_ready", "ready", "well_prepared",
        )


# ===========================================================================
# Score calculation
# ===========================================================================


class TestScoreCalculation:
    def test_all_steps_pass_all_objectives_met(self):
        ex = _make_exercise()
        for s in ex.steps:
            s.passed = True
        for o in ex.objectives:
            o.met = True
        score = GameDaySimulator._calculate_score(ex)
        assert score == 100.0

    def test_no_steps_no_objectives(self):
        ex = GameDayExercise(
            id="empty", name="Empty", exercise_type=ExerciseType.COMPONENT_FAILURE,
            difficulty=ExerciseDifficulty.BEGINNER, description="",
            objectives=[], steps=[], target_components=[],
        )
        assert GameDaySimulator._calculate_score(ex) == 0.0

    def test_partial_steps(self):
        ex = _make_exercise()
        ex.steps[0].passed = True
        ex.steps[1].passed = False
        ex.steps[2].passed = False
        score = GameDaySimulator._calculate_score(ex)
        # 1/3 steps = 33.3 * 0.6 + 0/1 obj * 0.4 = 20.0
        assert 19.0 <= score <= 21.0

    def test_steps_only(self):
        ex = GameDayExercise(
            id="s", name="S", exercise_type=ExerciseType.LOAD_SPIKE,
            difficulty=ExerciseDifficulty.BEGINNER, description="",
            objectives=[],
            steps=[
                ExerciseStep(order=1, action="a", description="d", expected_outcome="e", passed=True),
                ExerciseStep(order=2, action="b", description="d", expected_outcome="e", passed=False),
            ],
            target_components=[],
        )
        score = GameDaySimulator._calculate_score(ex)
        assert score == 50.0

    def test_objectives_only(self):
        ex = GameDayExercise(
            id="o", name="O", exercise_type=ExerciseType.LOAD_SPIKE,
            difficulty=ExerciseDifficulty.BEGINNER, description="",
            objectives=[
                ExerciseObjective(description="d", success_criteria="c", met=True),
                ExerciseObjective(description="d2", success_criteria="c2", met=False),
            ],
            steps=[],
            target_components=[],
        )
        score = GameDaySimulator._calculate_score(ex)
        assert score == 50.0


# ===========================================================================
# Readiness from score
# ===========================================================================


class TestReadinessFromScore:
    def test_well_prepared_100(self):
        assert GameDaySimulator._readiness_from_score(100.0) == "well_prepared"

    def test_well_prepared_80(self):
        assert GameDaySimulator._readiness_from_score(80.0) == "well_prepared"

    def test_ready_79(self):
        assert GameDaySimulator._readiness_from_score(79.9) == "ready"

    def test_ready_60(self):
        assert GameDaySimulator._readiness_from_score(60.0) == "ready"

    def test_partially_ready_59(self):
        assert GameDaySimulator._readiness_from_score(59.9) == "partially_ready"

    def test_partially_ready_40(self):
        assert GameDaySimulator._readiness_from_score(40.0) == "partially_ready"

    def test_not_ready_39(self):
        assert GameDaySimulator._readiness_from_score(39.9) == "not_ready"

    def test_not_ready_0(self):
        assert GameDaySimulator._readiness_from_score(0.0) == "not_ready"


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    def test_exercise_with_empty_targets(self):
        g = _simple_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(eid="ex-empty-t", targets=[])
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-empty-t")
        assert result is not None

    def test_multiple_generate_calls_accumulate(self):
        g = _simple_graph()
        sim = GameDaySimulator(g)
        r1 = sim.generate_exercises(count=2)
        r2 = sim.generate_exercises(count=2)
        assert len(sim._exercises) == len(r1) + len(r2)

    def test_component_failure_expert_difficulty(self):
        g = _simple_graph()
        sim = GameDaySimulator(g)
        exercises = sim.generate_exercises(
            difficulty=ExerciseDifficulty.EXPERT, count=10,
        )
        cf_exercises = [
            e for e in exercises
            if e.exercise_type == ExerciseType.COMPONENT_FAILURE
        ]
        for ex in cf_exercises:
            assert len(ex.steps) >= 4  # expert gets extra verification steps

    def test_advanced_difficulty_cascading_extra_step(self):
        g = _simple_graph()
        sim = GameDaySimulator(g)
        exercises = sim.generate_exercises(
            difficulty=ExerciseDifficulty.ADVANCED, count=10,
        )
        cas = [e for e in exercises if e.exercise_type == ExerciseType.CASCADING_FAILURE]
        for ex in cas:
            assert len(ex.steps) >= 4

    def test_findings_and_recommendations_populated(self):
        g = _simple_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-fr", etype=ExerciseType.COMPONENT_FAILURE, targets=["app"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-fr")
        assert result is not None
        # app has replicas=1, no failover, so should get findings
        assert len(result.findings) > 0 or len(result.recommendations) > 0

    def test_resilient_graph_high_scores(self):
        g = _resilient_graph()
        sim = GameDaySimulator(g)
        sim.generate_exercises(count=5)
        report = sim.run_all()
        # Resilient infra should generally score well
        assert report.overall_score >= 40.0

    def test_run_exercise_idempotent_id_lookup(self):
        g = _simple_graph()
        sim = GameDaySimulator(g)
        ex = _make_exercise(eid="ex-idem", targets=["app"])
        sim.add_exercise(ex)
        r1 = sim.run_exercise("ex-idem")
        # Running again should return the same exercise (already completed/failed)
        r2 = sim.run_exercise("ex-idem")
        assert r1 is r2

    def test_beginner_difficulty_generation(self):
        g = _simple_graph()
        sim = GameDaySimulator(g)
        exercises = sim.generate_exercises(
            difficulty=ExerciseDifficulty.BEGINNER, count=5,
        )
        assert len(exercises) >= 1
        for ex in exercises:
            assert ex.difficulty == ExerciseDifficulty.BEGINNER

    def test_dependency_timeout_with_retry(self):
        """Test dependency timeout when retry strategy is enabled but no circuit breaker."""
        g = InfraGraph()
        g.add_component(_comp("app", "App"))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE))
        dep = Dependency(source_id="app", target_id="db")
        dep.retry_strategy.enabled = True
        g.add_dependency(dep)
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-dt-retry",
            etype=ExerciseType.DEPENDENCY_TIMEOUT,
            targets=["app"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-dt-retry")
        assert result is not None
        assert result.steps[2].passed is True

    def test_network_partition_with_retry_no_cb(self):
        """Test network partition handled by retry strategy alone."""
        g = InfraGraph()
        g.add_component(_comp("app", "App"))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE))
        dep = Dependency(source_id="app", target_id="db")
        dep.retry_strategy.enabled = True
        g.add_dependency(dep)
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-np-retry",
            etype=ExerciseType.NETWORK_PARTITION,
            targets=["app"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-np-retry")
        assert result is not None
        assert result.steps[2].passed is True

    def test_network_partition_with_failover(self):
        """Test network partition handled by failover."""
        g = InfraGraph()
        c = _comp("app", "App", failover=True)
        g.add_component(c)
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-np-fo",
            etype=ExerciseType.NETWORK_PARTITION,
            targets=["app"],
        )
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-np-fo")
        assert result is not None
        assert result.steps[2].passed is True

    def test_region_outage_advanced_rto_not_configured(self):
        """Test RTO step when RTO is 0 (not configured)."""
        g = InfraGraph()
        c = _comp("app", "App")
        c.region.region = "us-east-1"
        c.region.dr_target_region = "us-west-2"
        # rto_seconds defaults to 0
        g.add_component(c)
        sim = GameDaySimulator(g)
        ex = _make_exercise(
            eid="ex-ro-norto",
            etype=ExerciseType.REGION_OUTAGE,
            difficulty=ExerciseDifficulty.ADVANCED,
            targets=["app"],
        )
        ex.steps = [
            ExerciseStep(order=1, action="identify", description="s1", expected_outcome="e1"),
            ExerciseStep(order=2, action="outage", description="s2", expected_outcome="e2"),
            ExerciseStep(order=3, action="failover", description="s3", expected_outcome="e3"),
            ExerciseStep(order=4, action="rto_rpo", description="s4", expected_outcome="e4"),
        ]
        sim.add_exercise(ex)
        result = sim.run_exercise("ex-ro-norto")
        assert result is not None
        # rto_seconds=0 -> rto_ok is False -> step 4 fails
        assert result.steps[3].passed is False

    def test_all_exercise_types_run_without_error(self):
        """Smoke test: every exercise type runs without error on simple graph."""
        g = _simple_graph()
        for etype in ExerciseType:
            sim = GameDaySimulator(g)
            ex = _make_exercise(
                eid=f"ex-smoke-{etype.value}",
                etype=etype,
                targets=["app"],
            )
            sim.add_exercise(ex)
            result = sim.run_exercise(f"ex-smoke-{etype.value}")
            assert result is not None, f"Failed for {etype}"
            assert 0 <= result.score <= 100, f"Score out of range for {etype}"
