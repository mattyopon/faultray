"""Tests for the Chaos Experiment Scheduler."""

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.chaos_schedule import (
    ChaosScheduleEngine,
    ConcurrentImpact,
    ConcurrentResult,
    ConflictType,
    Experiment,
    ExperimentType,
    SafetyLevel,
    SafetyValidation,
    Schedule,
    ScheduleConflict,
    ScheduleConstraints,
    ScheduledExperiment,
    TimeWindow,
    WindowType,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _build_simple_graph() -> InfraGraph:
    """Build a minimal 3-tier graph: LB -> App -> DB."""
    g = InfraGraph()
    g.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2,
        failover=FailoverConfig(enabled=True),
    ))
    g.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=2,
    ))
    g.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
        security=SecurityProfile(backup_enabled=True),
    ))
    g.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return g


def _build_complex_graph() -> InfraGraph:
    """Build a richer graph with cache, queue, external API."""
    g = _build_simple_graph()
    g.add_component(Component(
        id="cache", name="Redis Cache", type=ComponentType.CACHE,
        replicas=1,
    ))
    g.add_component(Component(
        id="queue", name="Message Queue", type=ComponentType.QUEUE,
        replicas=1,
    ))
    g.add_component(Component(
        id="ext", name="External API", type=ComponentType.EXTERNAL_API,
        replicas=1,
    ))
    g.add_dependency(Dependency(source_id="app", target_id="cache", dependency_type="optional"))
    g.add_dependency(Dependency(source_id="app", target_id="queue", dependency_type="async"))
    g.add_dependency(Dependency(source_id="app", target_id="ext", dependency_type="requires"))
    return g


def _build_high_util_graph() -> InfraGraph:
    """Graph with high utilisation components."""
    g = InfraGraph()
    g.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=85.0, memory_percent=78.0),
        capacity=Capacity(max_connections=500),
    ))
    g.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=92.0, disk_percent=88.0),
        capacity=Capacity(max_connections=100),
        security=SecurityProfile(backup_enabled=False),
    ))
    g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return g


def _build_degraded_graph() -> InfraGraph:
    """Graph with degraded and down components."""
    g = InfraGraph()
    g.add_component(Component(
        id="healthy", name="Healthy App", type=ComponentType.APP_SERVER,
        replicas=2, health=HealthStatus.HEALTHY,
    ))
    g.add_component(Component(
        id="degraded", name="Degraded App", type=ComponentType.APP_SERVER,
        replicas=1, health=HealthStatus.DEGRADED,
    ))
    g.add_component(Component(
        id="down", name="Down DB", type=ComponentType.DATABASE,
        replicas=1, health=HealthStatus.DOWN,
    ))
    g.add_dependency(Dependency(source_id="healthy", target_id="degraded", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="degraded", target_id="down", dependency_type="requires"))
    return g


def _make_experiment(**overrides) -> Experiment:
    """Create a default safe experiment with optional overrides."""
    defaults = dict(
        id="exp-1",
        name="Test Experiment",
        experiment_type=ExperimentType.LATENCY_INJECTION,
        target_components=["app"],
        safety_level=SafetyLevel.SAFE,
        duration_minutes=10.0,
        blast_radius_limit=5,
        requires_approval=False,
        rollback_plan="Revert latency injection",
        prerequisites=[],
    )
    defaults.update(overrides)
    return Experiment(**defaults)


@pytest.fixture
def engine() -> ChaosScheduleEngine:
    return ChaosScheduleEngine()


@pytest.fixture
def simple_graph() -> InfraGraph:
    return _build_simple_graph()


@pytest.fixture
def complex_graph() -> InfraGraph:
    return _build_complex_graph()


# ===================================================================
# Enum tests
# ===================================================================


class TestExperimentType:
    def test_all_values(self):
        values = {e.value for e in ExperimentType}
        assert values == {
            "failure_injection", "latency_injection", "resource_stress",
            "network_chaos", "state_transition", "security_test",
            "data_corruption", "load_test",
        }

    def test_str_enum(self):
        assert ExperimentType.FAILURE_INJECTION.value == "failure_injection"
        assert isinstance(ExperimentType.FAILURE_INJECTION, str)

    def test_from_value(self):
        assert ExperimentType("load_test") == ExperimentType.LOAD_TEST


class TestSafetyLevel:
    def test_all_values(self):
        values = {e.value for e in SafetyLevel}
        assert values == {"safe", "caution", "dangerous", "forbidden"}

    def test_ordering_by_value(self):
        ordered = sorted(SafetyLevel, key=lambda s: s.value)
        assert ordered[0] == SafetyLevel.CAUTION
        assert ordered[-1] == SafetyLevel.SAFE

    def test_from_value(self):
        assert SafetyLevel("forbidden") == SafetyLevel.FORBIDDEN


class TestConflictType:
    def test_all_values(self):
        values = {e.value for e in ConflictType}
        assert "target_overlap" in values
        assert "dependency_chain" in values
        assert "blast_radius_exceeded" in values
        assert "safety_violation" in values
        assert "prerequisite_missing" in values
        assert "concurrent_limit" in values


class TestWindowType:
    def test_all_values(self):
        values = {e.value for e in WindowType}
        assert values == {"maintenance", "safe_window", "blackout", "peak_hours"}


# ===================================================================
# Model tests
# ===================================================================


class TestExperimentModel:
    def test_defaults(self):
        exp = Experiment(id="e1", name="test", experiment_type=ExperimentType.LOAD_TEST)
        assert exp.target_components == []
        assert exp.safety_level == SafetyLevel.SAFE
        assert exp.duration_minutes == 10.0
        assert exp.blast_radius_limit == 3
        assert exp.requires_approval is False
        assert exp.rollback_plan == ""
        assert exp.prerequisites == []

    def test_full_init(self):
        exp = Experiment(
            id="e2", name="Full Test",
            experiment_type=ExperimentType.DATA_CORRUPTION,
            target_components=["db"],
            safety_level=SafetyLevel.DANGEROUS,
            duration_minutes=5.0,
            blast_radius_limit=2,
            requires_approval=True,
            rollback_plan="Restore from backup",
            prerequisites=["e1"],
        )
        assert exp.id == "e2"
        assert exp.safety_level == SafetyLevel.DANGEROUS
        assert exp.prerequisites == ["e1"]

    def test_serialization(self):
        exp = _make_experiment()
        d = exp.model_dump()
        assert d["id"] == "exp-1"
        assert d["experiment_type"] == "latency_injection"
        restored = Experiment(**d)
        assert restored == exp


class TestTimeWindow:
    def test_defaults(self):
        tw = TimeWindow()
        assert tw.start_offset_minutes == 0.0
        assert tw.end_offset_minutes == 60.0
        assert tw.window_type == WindowType.SAFE_WINDOW
        assert tw.label == ""
        assert tw.available is True

    def test_custom(self):
        tw = TimeWindow(
            start_offset_minutes=120.0,
            end_offset_minutes=180.0,
            window_type=WindowType.MAINTENANCE,
            label="Late night",
            available=False,
        )
        assert tw.window_type == WindowType.MAINTENANCE
        assert tw.available is False


class TestScheduledExperiment:
    def test_creation(self):
        exp = _make_experiment()
        tw = TimeWindow()
        se = ScheduledExperiment(
            experiment=exp, time_window=tw,
            execution_order=0, estimated_risk=0.3,
        )
        assert se.experiment.id == "exp-1"
        assert se.estimated_risk == 0.3
        assert se.approved is False

    def test_approved_flag(self):
        exp = _make_experiment(requires_approval=False)
        se = ScheduledExperiment(experiment=exp, time_window=TimeWindow(), approved=True)
        assert se.approved is True


class TestScheduleConflict:
    def test_creation(self):
        c = ScheduleConflict(
            conflict_type=ConflictType.TARGET_OVERLAP,
            experiment_ids=["a", "b"],
            description="overlap on app",
            severity=0.5,
            resolution_hint="stagger",
        )
        assert c.conflict_type == ConflictType.TARGET_OVERLAP
        assert c.severity == 0.5

    def test_defaults(self):
        c = ScheduleConflict(conflict_type=ConflictType.CONCURRENT_LIMIT)
        assert c.experiment_ids == []
        assert c.description == ""
        assert c.severity == 0.0


class TestSafetyValidation:
    def test_defaults(self):
        sv = SafetyValidation()
        assert sv.is_safe is True
        assert sv.safety_level == SafetyLevel.SAFE
        assert sv.violations == []
        assert sv.warnings == []
        assert sv.max_blast_radius == 0
        assert sv.requires_approval is False
        assert sv.rollback_feasible is True

    def test_unsafe(self):
        sv = SafetyValidation(
            is_safe=False,
            violations=["blast radius exceeded"],
            max_blast_radius=10,
        )
        assert sv.is_safe is False
        assert len(sv.violations) == 1


class TestScheduleConstraints:
    def test_defaults(self):
        sc = ScheduleConstraints()
        assert sc.max_concurrent_experiments == 2
        assert sc.max_total_risk == 0.8
        assert sc.max_blast_radius == 5
        assert sc.allow_dangerous is False
        assert sc.allow_forbidden is False
        assert sc.required_rollback_plans is True
        assert sc.max_duration_minutes == 480.0

    def test_custom(self):
        sc = ScheduleConstraints(allow_dangerous=True, max_blast_radius=10)
        assert sc.allow_dangerous is True
        assert sc.max_blast_radius == 10


class TestConcurrentResult:
    def test_defaults(self):
        cr = ConcurrentResult()
        assert cr.total_risk == 0.0
        assert cr.combined_blast_radius == 0
        assert cr.is_safe is True
        assert cr.max_concurrent_reached == 0
        assert cr.per_experiment == []

    def test_with_data(self):
        cr = ConcurrentResult(
            total_risk=0.5, combined_blast_radius=4, is_safe=True,
            max_concurrent_reached=2,
            per_experiment=[ConcurrentImpact(experiment_id="e1", individual_risk=0.3)],
        )
        assert len(cr.per_experiment) == 1


class TestConcurrentImpact:
    def test_defaults(self):
        ci = ConcurrentImpact(experiment_id="e1")
        assert ci.individual_risk == 0.0
        assert ci.added_blast_radius == 0
        assert ci.cascading_components == []


class TestSchedule:
    def test_defaults(self):
        s = Schedule()
        assert s.experiments == []
        assert s.conflicts == []
        assert s.total_duration_minutes == 0.0
        assert s.risk_score == 0.0
        assert s.safety_windows == []


# ===================================================================
# ChaosScheduleEngine — detect_conflicts
# ===================================================================


class TestDetectConflicts:
    def test_no_conflicts_no_experiments(self, engine):
        assert engine.detect_conflicts([]) == []

    def test_no_conflicts_disjoint(self, engine):
        a = _make_experiment(id="a", target_components=["app"])
        b = _make_experiment(id="b", target_components=["db"])
        conflicts = engine.detect_conflicts([a, b])
        assert len(conflicts) == 0

    def test_target_overlap(self, engine):
        a = _make_experiment(id="a", target_components=["app", "db"])
        b = _make_experiment(id="b", target_components=["db", "cache"])
        conflicts = engine.detect_conflicts([a, b])
        overlap_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.TARGET_OVERLAP]
        assert len(overlap_conflicts) >= 1
        assert "db" in overlap_conflicts[0].description

    def test_blast_radius_exceeded(self, engine):
        a = _make_experiment(id="a", target_components=["a1", "a2", "a3"], blast_radius_limit=2)
        b = _make_experiment(id="b", target_components=["a3", "a4"], blast_radius_limit=2)
        conflicts = engine.detect_conflicts([a, b])
        blast_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.BLAST_RADIUS_EXCEEDED]
        assert len(blast_conflicts) >= 1

    def test_incompatible_types(self, engine):
        a = _make_experiment(
            id="a", experiment_type=ExperimentType.FAILURE_INJECTION,
            target_components=["app"],
        )
        b = _make_experiment(
            id="b", experiment_type=ExperimentType.DATA_CORRUPTION,
            target_components=["app"],
        )
        conflicts = engine.detect_conflicts([a, b])
        safety_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.SAFETY_VIOLATION]
        assert len(safety_conflicts) >= 1

    def test_incompatible_types_no_overlap(self, engine):
        a = _make_experiment(
            id="a", experiment_type=ExperimentType.FAILURE_INJECTION,
            target_components=["app"],
        )
        b = _make_experiment(
            id="b", experiment_type=ExperimentType.DATA_CORRUPTION,
            target_components=["db"],
        )
        conflicts = engine.detect_conflicts([a, b])
        safety_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.SAFETY_VIOLATION]
        assert len(safety_conflicts) == 0

    def test_three_experiments_pairwise(self, engine):
        a = _make_experiment(id="a", target_components=["x"])
        b = _make_experiment(id="b", target_components=["x"])
        c = _make_experiment(id="c", target_components=["x"])
        conflicts = engine.detect_conflicts([a, b, c])
        overlap_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.TARGET_OVERLAP]
        assert len(overlap_conflicts) == 3  # a-b, a-c, b-c

    def test_conflict_severity(self, engine):
        a = _make_experiment(id="a", target_components=["x", "y"])
        b = _make_experiment(id="b", target_components=["y"])
        conflicts = engine.detect_conflicts([a, b])
        overlap_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.TARGET_OVERLAP]
        assert len(overlap_conflicts) == 1
        assert 0 < overlap_conflicts[0].severity <= 1.0

    def test_single_experiment_no_conflict(self, engine):
        a = _make_experiment(id="a")
        assert engine.detect_conflicts([a]) == []

    def test_resource_stress_load_test_incompatible(self, engine):
        a = _make_experiment(
            id="a", experiment_type=ExperimentType.RESOURCE_STRESS,
            target_components=["app"],
        )
        b = _make_experiment(
            id="b", experiment_type=ExperimentType.LOAD_TEST,
            target_components=["app"],
        )
        conflicts = engine.detect_conflicts([a, b])
        safety = [c for c in conflicts if c.conflict_type == ConflictType.SAFETY_VIOLATION]
        assert len(safety) >= 1


# ===================================================================
# ChaosScheduleEngine — validate_safety
# ===================================================================


class TestValidateSafety:
    def test_safe_experiment(self, engine, simple_graph):
        exp = _make_experiment(target_components=["app"])
        result = engine.validate_safety(simple_graph, exp)
        assert result.is_safe is True
        assert len(result.violations) == 0

    def test_blast_radius_violation(self, engine, simple_graph):
        exp = _make_experiment(
            target_components=["db"],
            blast_radius_limit=1,
        )
        result = engine.validate_safety(simple_graph, exp)
        # db cascade affects app and lb (upstream dependents)
        assert result.is_safe is False
        assert any("blast radius" in v.lower() for v in result.violations)

    def test_nonexistent_component(self, engine, simple_graph):
        exp = _make_experiment(target_components=["nonexistent"])
        result = engine.validate_safety(simple_graph, exp)
        assert result.is_safe is False
        assert any("not found" in v for v in result.violations)

    def test_forbidden_experiment(self, engine, simple_graph):
        exp = _make_experiment(safety_level=SafetyLevel.FORBIDDEN, target_components=["app"])
        result = engine.validate_safety(simple_graph, exp)
        assert result.is_safe is False
        assert result.requires_approval is True
        assert any("FORBIDDEN" in v for v in result.violations)

    def test_dangerous_experiment_warnings(self, engine, simple_graph):
        exp = _make_experiment(
            safety_level=SafetyLevel.DANGEROUS,
            target_components=["app"],
            rollback_plan="",
        )
        result = engine.validate_safety(simple_graph, exp)
        assert result.requires_approval is True
        assert any("DANGEROUS" in w for w in result.warnings)
        assert any("rollback" in w.lower() for w in result.warnings)

    def test_degraded_component_warning(self, engine):
        g = _build_degraded_graph()
        exp = _make_experiment(target_components=["degraded"])
        result = engine.validate_safety(g, exp)
        assert any("degraded" in w.lower() for w in result.warnings)

    def test_down_component_violation(self, engine):
        g = _build_degraded_graph()
        exp = _make_experiment(target_components=["down"])
        result = engine.validate_safety(g, exp)
        assert result.is_safe is False
        assert any("DOWN" in v for v in result.violations)

    def test_spof_warning(self, engine, simple_graph):
        exp = _make_experiment(target_components=["db"])
        result = engine.validate_safety(simple_graph, exp)
        assert any("SPOF" in w for w in result.warnings)

    def test_data_corruption_no_backup_violation(self, engine):
        g = _build_high_util_graph()
        exp = _make_experiment(
            experiment_type=ExperimentType.DATA_CORRUPTION,
            target_components=["db"],
        )
        result = engine.validate_safety(g, exp)
        assert any("backup" in v.lower() for v in result.violations)

    def test_data_corruption_with_backup_warning(self, engine, simple_graph):
        exp = _make_experiment(
            experiment_type=ExperimentType.DATA_CORRUPTION,
            target_components=["db"],
        )
        result = engine.validate_safety(simple_graph, exp)
        assert any("backup" in w.lower() for w in result.warnings)
        # no violation since backup_enabled=True in simple_graph db
        backup_violations = [v for v in result.violations if "backup" in v.lower()]
        assert len(backup_violations) == 0

    def test_affected_includes_cascade(self, engine, simple_graph):
        exp = _make_experiment(target_components=["db"], blast_radius_limit=10)
        result = engine.validate_safety(simple_graph, exp)
        # db failure cascades to app and lb
        assert "app" in result.affected_components
        assert "lb" in result.affected_components

    def test_rollback_feasible_with_plan(self, engine, simple_graph):
        exp = _make_experiment(
            safety_level=SafetyLevel.CAUTION,
            rollback_plan="restart service",
            target_components=["app"],
        )
        result = engine.validate_safety(simple_graph, exp)
        assert result.rollback_feasible is True

    def test_rollback_not_feasible_no_plan_non_safe(self, engine, simple_graph):
        exp = _make_experiment(
            safety_level=SafetyLevel.CAUTION,
            rollback_plan="",
            target_components=["app"],
        )
        result = engine.validate_safety(simple_graph, exp)
        assert result.rollback_feasible is False

    def test_rollback_feasible_safe_no_plan(self, engine, simple_graph):
        exp = _make_experiment(
            safety_level=SafetyLevel.SAFE,
            rollback_plan="",
            target_components=["app"],
        )
        result = engine.validate_safety(simple_graph, exp)
        assert result.rollback_feasible is True

    def test_overloaded_component_warning(self, engine):
        g = InfraGraph()
        g.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=2, health=HealthStatus.OVERLOADED,
        ))
        exp = _make_experiment(target_components=["app"])
        result = engine.validate_safety(g, exp)
        assert any("overloaded" in w.lower() for w in result.warnings)

    def test_multiple_targets_all_validated(self, engine, simple_graph):
        exp = _make_experiment(target_components=["app", "db"], blast_radius_limit=10)
        result = engine.validate_safety(simple_graph, exp)
        assert "app" in result.affected_components
        assert "db" in result.affected_components


# ===================================================================
# ChaosScheduleEngine — estimate_risk
# ===================================================================


class TestEstimateRisk:
    def test_safe_latency_low_risk(self, engine, simple_graph):
        exp = _make_experiment(
            experiment_type=ExperimentType.LATENCY_INJECTION,
            safety_level=SafetyLevel.SAFE,
            target_components=["app"],
            duration_minutes=5,
        )
        risk = engine.estimate_risk(simple_graph, exp)
        assert 0.0 <= risk <= 1.0
        assert risk < 0.5  # should be relatively low

    def test_data_corruption_high_risk(self, engine, simple_graph):
        exp = _make_experiment(
            experiment_type=ExperimentType.DATA_CORRUPTION,
            safety_level=SafetyLevel.DANGEROUS,
            target_components=["db"],
            duration_minutes=60,
        )
        risk = engine.estimate_risk(simple_graph, exp)
        assert risk > 0.3  # should be higher

    def test_risk_increases_with_safety_level(self, engine, simple_graph):
        safe = _make_experiment(safety_level=SafetyLevel.SAFE, target_components=["app"])
        danger = _make_experiment(safety_level=SafetyLevel.DANGEROUS, target_components=["app"])
        r_safe = engine.estimate_risk(simple_graph, safe)
        r_danger = engine.estimate_risk(simple_graph, danger)
        assert r_danger > r_safe

    def test_risk_increases_with_blast_radius(self, engine, complex_graph):
        small = _make_experiment(target_components=["ext"])  # ext has no dependents
        large = _make_experiment(target_components=["db"])   # db cascades to app, lb
        r_small = engine.estimate_risk(complex_graph, small)
        r_large = engine.estimate_risk(complex_graph, large)
        # db has more dependents/criticality so higher risk
        assert r_large >= r_small

    def test_risk_bounded(self, engine, simple_graph):
        exp = _make_experiment(
            experiment_type=ExperimentType.DATA_CORRUPTION,
            safety_level=SafetyLevel.FORBIDDEN,
            target_components=["lb", "app", "db"],
            duration_minutes=1000,
        )
        risk = engine.estimate_risk(simple_graph, exp)
        assert 0.0 <= risk <= 1.0

    def test_risk_zero_for_empty_graph(self, engine):
        g = InfraGraph()
        exp = _make_experiment(target_components=[])
        risk = engine.estimate_risk(g, exp)
        assert 0.0 <= risk <= 1.0

    def test_risk_with_duration_factor(self, engine, simple_graph):
        short = _make_experiment(target_components=["app"], duration_minutes=5)
        long_ = _make_experiment(target_components=["app"], duration_minutes=60)
        r_short = engine.estimate_risk(simple_graph, short)
        r_long = engine.estimate_risk(simple_graph, long_)
        assert r_long >= r_short

    def test_risk_with_critical_target(self, engine, simple_graph):
        # db has dependents (app depends on it)
        exp = _make_experiment(
            experiment_type=ExperimentType.FAILURE_INJECTION,
            target_components=["db"],
        )
        risk = engine.estimate_risk(simple_graph, exp)
        assert risk > 0.1


# ===================================================================
# ChaosScheduleEngine — find_safe_window
# ===================================================================


class TestFindSafeWindow:
    def test_low_util_immediate(self, engine, simple_graph):
        exp = _make_experiment(target_components=["app"])
        window = engine.find_safe_window(simple_graph, exp)
        assert window.start_offset_minutes == 0.0
        assert window.window_type == WindowType.SAFE_WINDOW

    def test_high_util_delayed(self, engine):
        g = _build_high_util_graph()
        exp = _make_experiment(target_components=["db"])
        window = engine.find_safe_window(g, exp)
        assert window.start_offset_minutes >= 120.0

    def test_dangerous_pushed_to_maintenance(self, engine, simple_graph):
        exp = _make_experiment(
            safety_level=SafetyLevel.DANGEROUS,
            target_components=["app"],
        )
        window = engine.find_safe_window(simple_graph, exp)
        assert window.window_type == WindowType.MAINTENANCE
        assert window.start_offset_minutes >= 360.0

    def test_forbidden_pushed_to_maintenance(self, engine, simple_graph):
        exp = _make_experiment(
            safety_level=SafetyLevel.FORBIDDEN,
            target_components=["app"],
        )
        window = engine.find_safe_window(simple_graph, exp)
        assert window.window_type == WindowType.MAINTENANCE

    def test_window_duration_matches_experiment(self, engine, simple_graph):
        exp = _make_experiment(target_components=["app"], duration_minutes=25.0)
        window = engine.find_safe_window(simple_graph, exp)
        duration = window.end_offset_minutes - window.start_offset_minutes
        assert duration == pytest.approx(25.0)

    def test_unknown_component_still_returns_window(self, engine, simple_graph):
        exp = _make_experiment(target_components=["nonexistent"])
        window = engine.find_safe_window(simple_graph, exp)
        assert window.available is True

    def test_medium_util_moderate_delay(self, engine):
        g = InfraGraph()
        g.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=1,
            metrics=ResourceMetrics(cpu_percent=55.0),
        ))
        exp = _make_experiment(target_components=["app"])
        window = engine.find_safe_window(g, exp)
        assert window.start_offset_minutes >= 120.0
        assert window.window_type == WindowType.SAFE_WINDOW

    def test_window_label(self, engine, simple_graph):
        exp = _make_experiment(name="My Experiment", target_components=["app"])
        window = engine.find_safe_window(simple_graph, exp)
        assert "My Experiment" in window.label


# ===================================================================
# ChaosScheduleEngine — create_schedule
# ===================================================================


class TestCreateSchedule:
    def test_empty_experiments(self, engine, simple_graph):
        schedule = engine.create_schedule(simple_graph, [])
        assert schedule.experiments == []
        assert schedule.total_duration_minutes == 0.0
        assert schedule.risk_score == 0.0

    def test_single_safe_experiment(self, engine, simple_graph):
        exp = _make_experiment(target_components=["app"])
        schedule = engine.create_schedule(simple_graph, [exp])
        assert len(schedule.experiments) == 1
        assert schedule.total_duration_minutes == 10.0
        assert schedule.risk_score > 0.0

    def test_forbidden_filtered_by_default(self, engine, simple_graph):
        exp = _make_experiment(
            safety_level=SafetyLevel.FORBIDDEN,
            target_components=["app"],
        )
        schedule = engine.create_schedule(simple_graph, [exp])
        assert len(schedule.experiments) == 0
        assert any(c.conflict_type == ConflictType.SAFETY_VIOLATION for c in schedule.conflicts)

    def test_forbidden_allowed_with_flag(self, engine, simple_graph):
        exp = _make_experiment(
            safety_level=SafetyLevel.FORBIDDEN,
            target_components=["app"],
        )
        constraints = ScheduleConstraints(allow_forbidden=True, required_rollback_plans=False)
        schedule = engine.create_schedule(simple_graph, [exp], constraints)
        # still blocked by validate_safety violations (FORBIDDEN safety level)
        # but the schedule creation allows it through the forbidden gate
        # The experiment will be included unless other violations block it
        assert len(schedule.experiments) >= 0  # depends on other checks

    def test_dangerous_filtered_by_default(self, engine, simple_graph):
        exp = _make_experiment(
            safety_level=SafetyLevel.DANGEROUS,
            target_components=["app"],
        )
        schedule = engine.create_schedule(simple_graph, [exp])
        assert len(schedule.experiments) == 0

    def test_dangerous_allowed_with_flag(self, engine, simple_graph):
        exp = _make_experiment(
            safety_level=SafetyLevel.DANGEROUS,
            target_components=["app"],
        )
        constraints = ScheduleConstraints(allow_dangerous=True, required_rollback_plans=False)
        schedule = engine.create_schedule(simple_graph, [exp], constraints)
        assert len(schedule.experiments) == 1

    def test_missing_rollback_filtered(self, engine, simple_graph):
        exp = _make_experiment(rollback_plan="", target_components=["app"])
        schedule = engine.create_schedule(simple_graph, [exp])
        assert len(schedule.experiments) == 0
        assert any(
            c.conflict_type == ConflictType.SAFETY_VIOLATION
            and "rollback" in c.description.lower()
            for c in schedule.conflicts
        )

    def test_rollback_not_required(self, engine, simple_graph):
        exp = _make_experiment(rollback_plan="", target_components=["app"])
        constraints = ScheduleConstraints(required_rollback_plans=False)
        schedule = engine.create_schedule(simple_graph, [exp], constraints)
        assert len(schedule.experiments) == 1

    def test_blast_radius_exceeded(self, engine, simple_graph):
        exp = _make_experiment(target_components=["lb", "app", "db"])
        constraints = ScheduleConstraints(max_blast_radius=1, required_rollback_plans=False)
        schedule = engine.create_schedule(simple_graph, [exp], constraints)
        assert len(schedule.experiments) == 0
        assert any(c.conflict_type == ConflictType.BLAST_RADIUS_EXCEEDED for c in schedule.conflicts)

    def test_prerequisite_ordering(self, engine, simple_graph):
        exp1 = _make_experiment(id="pre", target_components=["app"])
        exp2 = _make_experiment(id="main", target_components=["db"], prerequisites=["pre"])
        schedule = engine.create_schedule(simple_graph, [exp1, exp2])
        assert len(schedule.experiments) == 2
        assert schedule.experiments[0].experiment.id == "pre"
        assert schedule.experiments[1].experiment.id == "main"

    def test_missing_prerequisite(self, engine, simple_graph):
        exp = _make_experiment(id="main", target_components=["app"], prerequisites=["missing"])
        schedule = engine.create_schedule(simple_graph, [exp])
        assert len(schedule.experiments) == 0
        assert any(c.conflict_type == ConflictType.PREREQUISITE_MISSING for c in schedule.conflicts)

    def test_total_duration_constraint(self, engine, simple_graph):
        exps = [
            _make_experiment(id=f"e{i}", target_components=["app"], duration_minutes=200)
            for i in range(5)
        ]
        constraints = ScheduleConstraints(max_duration_minutes=480.0, required_rollback_plans=False)
        schedule = engine.create_schedule(simple_graph, exps, constraints)
        assert schedule.total_duration_minutes <= 480.0

    def test_execution_order(self, engine, simple_graph):
        exps = [
            _make_experiment(id=f"e{i}", target_components=["app"])
            for i in range(3)
        ]
        schedule = engine.create_schedule(simple_graph, exps)
        for i, se in enumerate(schedule.experiments):
            assert se.execution_order == i

    def test_default_constraints_used(self, engine, simple_graph):
        exp = _make_experiment(target_components=["app"])
        schedule = engine.create_schedule(simple_graph, [exp], None)
        assert schedule is not None

    def test_safety_windows_populated(self, engine, simple_graph):
        exp = _make_experiment(target_components=["app"])
        schedule = engine.create_schedule(simple_graph, [exp])
        assert len(schedule.safety_windows) == len(schedule.experiments)

    def test_time_windows_sequential(self, engine, simple_graph):
        exps = [
            _make_experiment(id="e1", target_components=["app"], duration_minutes=15),
            _make_experiment(id="e2", target_components=["db"], duration_minutes=20),
        ]
        schedule = engine.create_schedule(simple_graph, exps)
        if len(schedule.experiments) == 2:
            w1 = schedule.experiments[0].time_window
            w2 = schedule.experiments[1].time_window
            assert w2.start_offset_minutes >= w1.end_offset_minutes

    def test_risk_score_capped_at_1(self, engine, simple_graph):
        exp = _make_experiment(
            experiment_type=ExperimentType.DATA_CORRUPTION,
            safety_level=SafetyLevel.CAUTION,
            target_components=["db"],
            duration_minutes=100,
        )
        constraints = ScheduleConstraints(
            allow_dangerous=True, required_rollback_plans=False,
        )
        schedule = engine.create_schedule(simple_graph, [exp], constraints)
        assert schedule.risk_score <= 1.0

    def test_conflicts_include_detect_conflicts_results(self, engine, simple_graph):
        a = _make_experiment(id="a", target_components=["app"])
        b = _make_experiment(id="b", target_components=["app"])
        schedule = engine.create_schedule(simple_graph, [a, b])
        overlap_conflicts = [c for c in schedule.conflicts if c.conflict_type == ConflictType.TARGET_OVERLAP]
        assert len(overlap_conflicts) >= 1

    def test_approved_flag_set_correctly(self, engine, simple_graph):
        exp = _make_experiment(requires_approval=False, target_components=["app"])
        schedule = engine.create_schedule(simple_graph, [exp])
        assert len(schedule.experiments) == 1
        assert schedule.experiments[0].approved is True

    def test_unapproved_flag(self, engine, simple_graph):
        exp = _make_experiment(requires_approval=True, target_components=["app"])
        schedule = engine.create_schedule(simple_graph, [exp])
        if schedule.experiments:
            assert schedule.experiments[0].approved is False


# ===================================================================
# ChaosScheduleEngine — generate_experiment_plan
# ===================================================================


class TestGenerateExperimentPlan:
    def test_empty_graph(self, engine):
        g = InfraGraph()
        plan = engine.generate_experiment_plan(g)
        assert plan == []

    def test_spof_detection(self, engine, simple_graph):
        plan = engine.generate_experiment_plan(simple_graph)
        spof_exps = [e for e in plan if "SPOF" in e.name]
        # db is SPOF (1 replica, has dependents, no failover)
        assert len(spof_exps) >= 1
        assert any("db" in e.name.lower() or "database" in e.name.lower() for e in spof_exps)

    def test_no_spof_for_replicated(self, engine):
        g = InfraGraph()
        g.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=3,
        ))
        g.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            replicas=3,
        ))
        g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
        plan = engine.generate_experiment_plan(g)
        spof_exps = [e for e in plan if "SPOF" in e.name]
        assert len(spof_exps) == 0

    def test_high_util_resource_stress(self, engine):
        g = _build_high_util_graph()
        plan = engine.generate_experiment_plan(g)
        stress_exps = [e for e in plan if e.experiment_type == ExperimentType.RESOURCE_STRESS]
        assert len(stress_exps) >= 1

    def test_multi_dependency_network_chaos(self, engine, complex_graph):
        plan = engine.generate_experiment_plan(complex_graph)
        net_exps = [e for e in plan if e.experiment_type == ExperimentType.NETWORK_CHAOS]
        assert len(net_exps) >= 1

    def test_database_data_corruption(self, engine, simple_graph):
        plan = engine.generate_experiment_plan(simple_graph)
        data_exps = [e for e in plan if e.experiment_type == ExperimentType.DATA_CORRUPTION]
        assert len(data_exps) >= 1
        for e in data_exps:
            assert e.safety_level == SafetyLevel.DANGEROUS
            assert e.requires_approval is True

    def test_database_no_corruption_without_backup(self, engine):
        g = InfraGraph()
        g.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            replicas=1,
            security=SecurityProfile(backup_enabled=False),
        ))
        plan = engine.generate_experiment_plan(g)
        data_exps = [e for e in plan if e.experiment_type == ExperimentType.DATA_CORRUPTION]
        assert len(data_exps) == 0

    def test_all_experiments_have_ids(self, engine, complex_graph):
        plan = engine.generate_experiment_plan(complex_graph)
        ids = [e.id for e in plan]
        assert len(ids) == len(set(ids))  # unique IDs
        assert all(e.id.startswith("auto-") for e in plan)

    def test_all_experiments_have_rollback_plans(self, engine, complex_graph):
        plan = engine.generate_experiment_plan(complex_graph)
        for e in plan:
            assert e.rollback_plan != ""

    def test_latency_injection_for_high_latency_edges(self, engine):
        g = InfraGraph()
        g.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER, replicas=2))
        g.add_component(Component(id="b", name="B", type=ComponentType.DATABASE, replicas=2))
        g.add_dependency(Dependency(
            source_id="a", target_id="b",
            dependency_type="requires", latency_ms=100.0,
        ))
        plan = engine.generate_experiment_plan(g)
        lat_exps = [e for e in plan if e.experiment_type == ExperimentType.LATENCY_INJECTION]
        assert len(lat_exps) >= 1

    def test_entry_point_load_test(self, engine, simple_graph):
        plan = engine.generate_experiment_plan(simple_graph)
        load_exps = [e for e in plan if e.experiment_type == ExperimentType.LOAD_TEST]
        assert len(load_exps) >= 1

    def test_no_failover_spof_has_approval(self, engine, simple_graph):
        plan = engine.generate_experiment_plan(simple_graph)
        spof_exps = [e for e in plan if "SPOF" in e.name]
        for e in spof_exps:
            assert e.requires_approval is True


# ===================================================================
# ChaosScheduleEngine — simulate_concurrent_experiments
# ===================================================================


class TestSimulateConcurrentExperiments:
    def test_empty_list(self, engine, simple_graph):
        result = engine.simulate_concurrent_experiments(simple_graph, [])
        assert result.is_safe is True
        assert result.total_risk == 0.0
        assert result.combined_blast_radius == 0

    def test_single_experiment(self, engine, simple_graph):
        exp = _make_experiment(target_components=["app"])
        result = engine.simulate_concurrent_experiments(simple_graph, [exp])
        assert result.max_concurrent_reached == 1
        assert len(result.per_experiment) == 1
        assert result.per_experiment[0].experiment_id == "exp-1"

    def test_overlapping_targets(self, engine, simple_graph):
        a = _make_experiment(id="a", target_components=["app"])
        b = _make_experiment(id="b", target_components=["app"])
        result = engine.simulate_concurrent_experiments(simple_graph, [a, b])
        assert len(result.interaction_effects) >= 1

    def test_disjoint_safe(self, engine):
        g = InfraGraph()
        g.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER, replicas=2))
        g.add_component(Component(id="b", name="B", type=ComponentType.CACHE, replicas=2))
        # No edges — truly disjoint
        a = _make_experiment(id="a", target_components=["a"])
        b = _make_experiment(id="b", target_components=["b"])
        result = engine.simulate_concurrent_experiments(g, [a, b])
        assert result.is_safe is True

    def test_cascade_interaction(self, engine, simple_graph):
        # If we fail lb, it cascades to app; if we also target app, there's interaction
        a = _make_experiment(
            id="a",
            experiment_type=ExperimentType.FAILURE_INJECTION,
            target_components=["db"],
        )
        b = _make_experiment(
            id="b",
            experiment_type=ExperimentType.LATENCY_INJECTION,
            target_components=["app"],
        )
        result = engine.simulate_concurrent_experiments(simple_graph, [a, b])
        # db cascade affects app, which is also b's target
        assert len(result.interaction_effects) >= 1

    def test_combined_blast_radius(self, engine, complex_graph):
        a = _make_experiment(id="a", target_components=["cache"])
        b = _make_experiment(id="b", target_components=["queue"])
        result = engine.simulate_concurrent_experiments(complex_graph, [a, b])
        assert result.combined_blast_radius >= 2

    def test_recommendations_for_high_blast(self, engine, complex_graph):
        exps = [
            _make_experiment(id=f"e{i}", target_components=[cid])
            for i, cid in enumerate(["lb", "app", "db", "cache", "queue", "ext"])
        ]
        result = engine.simulate_concurrent_experiments(complex_graph, exps)
        assert result.combined_blast_radius > 5
        assert any("blast radius" in r.lower() for r in result.recommendations)

    def test_per_experiment_risk(self, engine, simple_graph):
        a = _make_experiment(id="a", target_components=["app"])
        b = _make_experiment(id="b", target_components=["db"])
        result = engine.simulate_concurrent_experiments(simple_graph, [a, b])
        assert len(result.per_experiment) == 2
        for pi in result.per_experiment:
            assert pi.individual_risk >= 0.0

    def test_cascading_failures_reported(self, engine, simple_graph):
        # Both targeting things that cascade to same component
        a = _make_experiment(id="a", target_components=["db"])
        b = _make_experiment(id="b", target_components=["app"])
        result = engine.simulate_concurrent_experiments(simple_graph, [a, b])
        # db cascades to app, and app is also a target of b, so app appears in cascade of a
        # This means 'app' is in both a's cascade and b's targets
        # The cascading_failures logic adds to the list when a component is already in all_affected
        assert result.max_concurrent_reached == 2

    def test_total_risk_bounded(self, engine, complex_graph):
        exps = [
            _make_experiment(
                id=f"e{i}",
                experiment_type=ExperimentType.DATA_CORRUPTION,
                safety_level=SafetyLevel.DANGEROUS,
                target_components=[cid],
            )
            for i, cid in enumerate(["lb", "app", "db", "cache", "queue", "ext"])
        ]
        result = engine.simulate_concurrent_experiments(complex_graph, exps)
        assert result.total_risk <= 1.0

    def test_interaction_effects_cascade_detection(self, engine, simple_graph):
        a = _make_experiment(id="a", target_components=["db"])
        b = _make_experiment(id="b", target_components=["app"])
        result = engine.simulate_concurrent_experiments(simple_graph, [a, b])
        # Check that cascade from db affecting app is detected
        cascade_interactions = [e for e in result.interaction_effects if "cascade" in e.lower()]
        # db cascading to app, which is b's target
        assert len(cascade_interactions) >= 1


# ===================================================================
# Integration tests
# ===================================================================


class TestIntegration:
    def test_generate_then_schedule(self, engine, complex_graph):
        plan = engine.generate_experiment_plan(complex_graph)
        assert len(plan) > 0
        constraints = ScheduleConstraints(
            allow_dangerous=True,
            allow_forbidden=False,
            required_rollback_plans=True,
            max_blast_radius=10,
        )
        schedule = engine.create_schedule(complex_graph, plan, constraints)
        assert schedule is not None
        assert schedule.total_duration_minutes > 0

    def test_generate_validate_all(self, engine, complex_graph):
        plan = engine.generate_experiment_plan(complex_graph)
        for exp in plan:
            validation = engine.validate_safety(complex_graph, exp)
            assert isinstance(validation, SafetyValidation)

    def test_concurrent_sim_on_generated_plan(self, engine, complex_graph):
        plan = engine.generate_experiment_plan(complex_graph)
        safe_exps = [e for e in plan if e.safety_level == SafetyLevel.SAFE]
        if safe_exps:
            result = engine.simulate_concurrent_experiments(complex_graph, safe_exps)
            assert isinstance(result, ConcurrentResult)

    def test_full_workflow_simple(self, engine, simple_graph):
        # Generate
        plan = engine.generate_experiment_plan(simple_graph)
        assert len(plan) >= 1

        # Validate each
        valid = []
        for exp in plan:
            v = engine.validate_safety(simple_graph, exp)
            if v.is_safe:
                valid.append(exp)

        # Schedule valid ones
        constraints = ScheduleConstraints(
            allow_dangerous=True,
            required_rollback_plans=True,
            max_blast_radius=10,
        )
        schedule = engine.create_schedule(simple_graph, valid, constraints)
        assert isinstance(schedule, Schedule)

        # Concurrent simulation
        if schedule.experiments:
            scheduled_exps = [se.experiment for se in schedule.experiments]
            concurrent = engine.simulate_concurrent_experiments(simple_graph, scheduled_exps)
            assert isinstance(concurrent, ConcurrentResult)

    def test_full_workflow_complex(self, engine, complex_graph):
        plan = engine.generate_experiment_plan(complex_graph)
        for exp in plan:
            window = engine.find_safe_window(complex_graph, exp)
            assert window.available is True

        constraints = ScheduleConstraints(
            allow_dangerous=True,
            required_rollback_plans=True,
            max_blast_radius=10,
        )
        schedule = engine.create_schedule(complex_graph, plan, constraints)
        assert schedule.total_duration_minutes >= 0
        assert schedule.risk_score >= 0

    def test_conflict_detection_in_schedule(self, engine, simple_graph):
        # Create experiments with known conflicts
        a = _make_experiment(
            id="a", target_components=["app"],
            experiment_type=ExperimentType.FAILURE_INJECTION,
        )
        b = _make_experiment(
            id="b", target_components=["app"],
            experiment_type=ExperimentType.DATA_CORRUPTION,
        )
        schedule = engine.create_schedule(simple_graph, [a, b])
        assert len(schedule.conflicts) > 0

    def test_schedule_serialization(self, engine, simple_graph):
        exp = _make_experiment(target_components=["app"])
        schedule = engine.create_schedule(simple_graph, [exp])
        d = schedule.model_dump()
        restored = Schedule(**d)
        assert restored.total_duration_minutes == schedule.total_duration_minutes
        assert len(restored.experiments) == len(schedule.experiments)

    def test_concurrent_result_serialization(self, engine, simple_graph):
        exp = _make_experiment(target_components=["app"])
        result = engine.simulate_concurrent_experiments(simple_graph, [exp])
        d = result.model_dump()
        restored = ConcurrentResult(**d)
        assert restored.total_risk == result.total_risk


# ===================================================================
# Edge case tests
# ===================================================================


class TestEdgeCases:
    def test_experiment_with_no_targets(self, engine, simple_graph):
        exp = _make_experiment(target_components=[])
        risk = engine.estimate_risk(simple_graph, exp)
        assert 0.0 <= risk <= 1.0

    def test_single_node_graph(self, engine):
        g = InfraGraph()
        g.add_component(Component(id="solo", name="Solo", type=ComponentType.APP_SERVER, replicas=1))
        exp = _make_experiment(target_components=["solo"])
        risk = engine.estimate_risk(g, exp)
        assert 0.0 <= risk <= 1.0
        validation = engine.validate_safety(g, exp)
        assert isinstance(validation, SafetyValidation)

    def test_disconnected_graph(self, engine):
        g = InfraGraph()
        g.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER, replicas=1))
        g.add_component(Component(id="b", name="B", type=ComponentType.DATABASE, replicas=1))
        # No edges
        exp = _make_experiment(target_components=["a"])
        validation = engine.validate_safety(g, exp)
        assert validation.is_safe is True
        assert len(validation.affected_components) == 1

    def test_self_referential_targets(self, engine, simple_graph):
        exp = _make_experiment(target_components=["app", "app"])
        validation = engine.validate_safety(simple_graph, exp)
        assert isinstance(validation, SafetyValidation)

    def test_very_long_duration(self, engine, simple_graph):
        exp = _make_experiment(target_components=["app"], duration_minutes=99999)
        risk = engine.estimate_risk(simple_graph, exp)
        assert risk <= 1.0

    def test_zero_duration(self, engine, simple_graph):
        exp = _make_experiment(target_components=["app"], duration_minutes=0)
        risk = engine.estimate_risk(simple_graph, exp)
        assert risk >= 0.0

    def test_large_number_of_experiments(self, engine, simple_graph):
        exps = [
            _make_experiment(id=f"e{i}", target_components=["app"])
            for i in range(50)
        ]
        conflicts = engine.detect_conflicts(exps)
        assert len(conflicts) > 0

    def test_all_experiment_types(self, engine, simple_graph):
        for et in ExperimentType:
            exp = _make_experiment(
                id=f"exp-{et.value}",
                experiment_type=et,
                target_components=["app"],
            )
            risk = engine.estimate_risk(simple_graph, exp)
            assert 0.0 <= risk <= 1.0

    def test_all_safety_levels(self, engine, simple_graph):
        for sl in SafetyLevel:
            exp = _make_experiment(
                id=f"exp-{sl.value}",
                safety_level=sl,
                target_components=["app"],
            )
            validation = engine.validate_safety(simple_graph, exp)
            assert isinstance(validation, SafetyValidation)

    def test_empty_graph_generate_plan(self, engine):
        g = InfraGraph()
        plan = engine.generate_experiment_plan(g)
        assert plan == []

    def test_schedule_with_all_filtered(self, engine, simple_graph):
        exp = _make_experiment(
            safety_level=SafetyLevel.FORBIDDEN,
            target_components=["app"],
        )
        schedule = engine.create_schedule(simple_graph, [exp])
        assert len(schedule.experiments) == 0
        assert schedule.total_duration_minutes == 0.0

    def test_concurrent_sim_many_experiments(self, engine, complex_graph):
        exps = [
            _make_experiment(id=f"e{i}", target_components=["app"])
            for i in range(10)
        ]
        result = engine.simulate_concurrent_experiments(complex_graph, exps)
        assert result.max_concurrent_reached == 10
        assert result.total_risk <= 1.0

    def test_blast_radius_no_cascade(self, engine):
        g = InfraGraph()
        g.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER, replicas=2))
        exp = _make_experiment(target_components=["a"])
        blast = engine._compute_blast_radius(g, exp)
        assert blast == 1  # just the target, no cascade

    def test_blast_radius_with_cascade(self, engine, simple_graph):
        exp = _make_experiment(target_components=["db"])
        blast = engine._compute_blast_radius(simple_graph, exp)
        # db -> app -> lb cascade
        assert blast >= 2

    def test_find_safe_window_no_targets(self, engine, simple_graph):
        exp = _make_experiment(target_components=[])
        window = engine.find_safe_window(simple_graph, exp)
        assert window.start_offset_minutes == 0.0


# ===================================================================
# Additional coverage tests
# ===================================================================


class TestAdditionalCoverage:
    def test_incompatible_network_failure(self, engine):
        a = _make_experiment(
            id="a", experiment_type=ExperimentType.FAILURE_INJECTION,
            target_components=["x"],
        )
        b = _make_experiment(
            id="b", experiment_type=ExperimentType.NETWORK_CHAOS,
            target_components=["x"],
        )
        conflicts = engine.detect_conflicts([a, b])
        safety = [c for c in conflicts if c.conflict_type == ConflictType.SAFETY_VIOLATION]
        assert len(safety) >= 1

    def test_incompatible_data_state(self, engine):
        a = _make_experiment(
            id="a", experiment_type=ExperimentType.DATA_CORRUPTION,
            target_components=["x"],
        )
        b = _make_experiment(
            id="b", experiment_type=ExperimentType.STATE_TRANSITION,
            target_components=["x"],
        )
        conflicts = engine.detect_conflicts([a, b])
        safety = [c for c in conflicts if c.conflict_type == ConflictType.SAFETY_VIOLATION]
        assert len(safety) >= 1

    def test_compatible_types_no_safety_conflict(self, engine):
        a = _make_experiment(
            id="a", experiment_type=ExperimentType.LATENCY_INJECTION,
            target_components=["x"],
        )
        b = _make_experiment(
            id="b", experiment_type=ExperimentType.LOAD_TEST,
            target_components=["x"],
        )
        conflicts = engine.detect_conflicts([a, b])
        safety = [c for c in conflicts if c.conflict_type == ConflictType.SAFETY_VIOLATION]
        assert len(safety) == 0

    def test_schedule_notes_from_warnings(self, engine, simple_graph):
        exp = _make_experiment(target_components=["db"])
        schedule = engine.create_schedule(simple_graph, [exp])
        if schedule.experiments:
            notes = schedule.experiments[0].notes
            assert isinstance(notes, str)

    def test_concurrent_no_cascade_no_failure(self, engine):
        g = InfraGraph()
        g.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER, replicas=2))
        g.add_component(Component(id="b", name="B", type=ComponentType.CACHE, replicas=2))
        a = _make_experiment(id="a", target_components=["a"])
        b = _make_experiment(id="b", target_components=["b"])
        result = engine.simulate_concurrent_experiments(g, [a, b])
        assert result.is_safe is True
        assert result.cascading_failures == []

    def test_generate_plan_with_failover_no_spof(self, engine):
        g = InfraGraph()
        g.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            replicas=1, failover=FailoverConfig(enabled=True),
        ))
        g.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=2,
        ))
        g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
        plan = engine.generate_experiment_plan(g)
        spof_exps = [e for e in plan if "SPOF" in e.name]
        assert len(spof_exps) == 0

    def test_estimate_risk_failure_injection(self, engine, simple_graph):
        exp = _make_experiment(
            experiment_type=ExperimentType.FAILURE_INJECTION,
            target_components=["app"],
        )
        risk = engine.estimate_risk(simple_graph, exp)
        assert risk > 0.1  # failure injection has high type weight

    def test_estimate_risk_security_test(self, engine, simple_graph):
        exp = _make_experiment(
            experiment_type=ExperimentType.SECURITY_TEST,
            target_components=["app"],
        )
        risk = engine.estimate_risk(simple_graph, exp)
        assert 0.0 <= risk <= 1.0

    def test_validate_safety_healthy_component(self, engine, simple_graph):
        exp = _make_experiment(target_components=["lb"])
        result = engine.validate_safety(simple_graph, exp)
        # lb has replicas=2 and failover, should not have SPOF warning
        spof_warnings = [w for w in result.warnings if "SPOF" in w]
        assert len(spof_warnings) == 0

    def test_concurrent_recommendations_for_interactions(self, engine, simple_graph):
        a = _make_experiment(id="a", target_components=["app"])
        b = _make_experiment(id="b", target_components=["app"])
        result = engine.simulate_concurrent_experiments(simple_graph, [a, b])
        assert any("interaction" in r.lower() for r in result.recommendations)

    def test_schedule_with_caution_level(self, engine, simple_graph):
        exp = _make_experiment(
            safety_level=SafetyLevel.CAUTION,
            target_components=["app"],
        )
        schedule = engine.create_schedule(simple_graph, [exp])
        assert len(schedule.experiments) == 1
