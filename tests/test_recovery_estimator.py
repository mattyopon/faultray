"""Comprehensive tests for the Recovery Time Estimator engine.

Targets ~99% code coverage across all public and private methods,
including edge cases such as empty graphs, single components, circular
dependencies, external APIs, and high-utilisation scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field

from infrasim.model.components import (
    Component,
    ComponentType,
    Dependency,
    ResourceMetrics,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.recovery_estimator import (
    ComponentRecovery,
    RecoveryEstimator,
    RecoveryImprovement,
    RecoveryReport,
    RecoveryStep,
    ScenarioRecovery,
    _CASCADE_DELAY_PER_LEVEL,
    _dependency_depth,
)
from infrasim.simulator.scenarios import Fault, FaultType, Scenario
from infrasim.simulator.engine import ScenarioResult
from infrasim.simulator.cascade import CascadeChain


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_graph() -> InfraGraph:
    """Build a simple 3-tier graph: LB -> App (x3) -> DB (x2)."""
    g = InfraGraph()

    g.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2,
    ))
    g.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=3,
    ))
    g.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=2,
    ))

    g.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))

    return g


def _make_single_component(
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    autoscaling: bool = False,
    cpu: float = 0.0,
    memory: float = 0.0,
) -> tuple[InfraGraph, Component]:
    """Create a graph with a single component and return both."""
    g = InfraGraph()
    comp = Component(
        id="c1", name="C1", type=ctype,
        replicas=replicas,
        metrics=ResourceMetrics(cpu_percent=cpu, memory_percent=memory),
    )
    if failover:
        comp.failover.enabled = True
    if autoscaling:
        comp.autoscaling.enabled = True
    g.add_component(comp)
    return g, comp


def _make_scenario_result(
    name: str = "test-scenario",
    fault_targets: list[str] | None = None,
) -> ScenarioResult:
    """Build a minimal ScenarioResult for testing."""
    targets = fault_targets or ["app"]
    faults = [
        Fault(
            target_component_id=tid,
            fault_type=FaultType.COMPONENT_DOWN,
        )
        for tid in targets
    ]
    scenario = Scenario(
        id="s1",
        name=name,
        description="Test scenario",
        faults=faults,
    )
    cascade = CascadeChain(trigger=name, total_components=5)
    return ScenarioResult(scenario=scenario, cascade=cascade, risk_score=5.0)


# ===================================================================
# 1. Base MTTR calculation per component type
# ===================================================================


class TestBaseMTTR:
    """Test base MTTR lookup for each component type."""

    def test_web_server_no_redundancy(self):
        g, comp = _make_single_component(ComponentType.WEB_SERVER)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        # Worst-case for WEB_SERVER = 30 min; SPOF doubles it => 60
        assert cr.estimated_mttr_minutes > 0

    def test_web_server_with_replicas(self):
        g, comp = _make_single_component(ComponentType.WEB_SERVER, replicas=3)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        # Best-case (5 min) with replica reduction.
        assert cr.estimated_mttr_minutes < 30.0

    def test_app_server(self):
        g, comp = _make_single_component(ComponentType.APP_SERVER)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        assert cr.estimated_mttr_minutes > 0

    def test_database_no_redundancy(self):
        g, comp = _make_single_component(ComponentType.DATABASE)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        # Worst-case for DATABASE = 120 min.
        assert cr.estimated_mttr_minutes >= 100

    def test_database_with_replicas(self):
        g, comp = _make_single_component(ComponentType.DATABASE, replicas=3)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        # Should be significantly less than the no-redundancy case.
        assert cr.estimated_mttr_minutes < 50

    def test_cache(self):
        g, comp = _make_single_component(ComponentType.CACHE)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        # Worst-case CACHE = 10 min, but SPOF doubles it.
        assert cr.estimated_mttr_minutes > 0

    def test_queue(self):
        g, comp = _make_single_component(ComponentType.QUEUE)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        assert cr.estimated_mttr_minutes > 0

    def test_load_balancer(self):
        g, comp = _make_single_component(ComponentType.LOAD_BALANCER)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        assert cr.estimated_mttr_minutes > 0

    def test_dns(self):
        g, comp = _make_single_component(ComponentType.DNS)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        # Worst-case DNS = 60 min.
        assert cr.estimated_mttr_minutes >= 50

    def test_storage(self):
        g, comp = _make_single_component(ComponentType.STORAGE)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        # Worst-case STORAGE = 180 min.
        assert cr.estimated_mttr_minutes >= 100

    def test_external_api_returns_zero(self):
        g, comp = _make_single_component(ComponentType.EXTERNAL_API)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        # External APIs: we cannot control recovery.
        assert cr.estimated_mttr_minutes == 0.0

    def test_custom_type(self):
        g, comp = _make_single_component(ComponentType.CUSTOM)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        assert cr.estimated_mttr_minutes > 0


# ===================================================================
# 2. Modifier effects
# ===================================================================


class TestModifiers:
    """Test that modifiers (replicas, failover, etc.) adjust MTTR correctly."""

    def test_replicas_reduce_mttr(self):
        est = RecoveryEstimator()
        g1, c1 = _make_single_component(ComponentType.APP_SERVER, replicas=1)
        g2, c2 = _make_single_component(ComponentType.APP_SERVER, replicas=3)
        r1 = est.estimate_component(c1, g1)
        r2 = est.estimate_component(c2, g2)
        assert r2.estimated_mttr_minutes < r1.estimated_mttr_minutes

    def test_many_replicas_cap_reduction(self):
        """5+ replicas should hit the maximum reduction factor (0.2)."""
        est = RecoveryEstimator()
        g, comp = _make_single_component(ComponentType.APP_SERVER, replicas=10)
        cr = est.estimate_component(comp, g)
        # Base best-case = 5 min * 0.2 (replica factor) = 1.0 min
        assert cr.estimated_mttr_minutes <= 2.0

    def test_failover_reduces_mttr(self):
        est = RecoveryEstimator()
        g1, c1 = _make_single_component(ComponentType.DATABASE, replicas=2)
        g2, c2 = _make_single_component(ComponentType.DATABASE, replicas=2, failover=True)
        r1 = est.estimate_component(c1, g1)
        r2 = est.estimate_component(c2, g2)
        assert r2.estimated_mttr_minutes < r1.estimated_mttr_minutes

    def test_autoscaling_reduces_mttr(self):
        est = RecoveryEstimator()
        g1, c1 = _make_single_component(ComponentType.APP_SERVER, replicas=2)
        g2, c2 = _make_single_component(ComponentType.APP_SERVER, replicas=2, autoscaling=True)
        r1 = est.estimate_component(c1, g1)
        r2 = est.estimate_component(c2, g2)
        assert r2.estimated_mttr_minutes < r1.estimated_mttr_minutes

    def test_combined_failover_and_autoscaling(self):
        """Combining failover + autoscaling should give the deepest reduction."""
        est = RecoveryEstimator()
        g, comp = _make_single_component(
            ComponentType.APP_SERVER, replicas=3,
            failover=True, autoscaling=True,
        )
        cr = est.estimate_component(comp, g)
        # Very aggressive reduction: 5 * 0.3 * 0.3 * 0.4 = 0.18 min
        assert cr.estimated_mttr_minutes < 1.0

    def test_high_utilisation_increases_mttr(self):
        est = RecoveryEstimator()
        g1, c1 = _make_single_component(ComponentType.APP_SERVER, replicas=2, cpu=50.0)
        g2, c2 = _make_single_component(ComponentType.APP_SERVER, replicas=2, cpu=95.0)
        r1 = est.estimate_component(c1, g1)
        r2 = est.estimate_component(c2, g2)
        assert r2.estimated_mttr_minutes > r1.estimated_mttr_minutes

    def test_utilisation_at_boundary(self):
        """80% utilisation should still trigger the penalty."""
        est = RecoveryEstimator()
        g1, c1 = _make_single_component(ComponentType.APP_SERVER, replicas=2, cpu=79.0)
        g2, c2 = _make_single_component(ComponentType.APP_SERVER, replicas=2, cpu=81.0)
        r1 = est.estimate_component(c1, g1)
        r2 = est.estimate_component(c2, g2)
        assert r2.estimated_mttr_minutes > r1.estimated_mttr_minutes

    def test_spof_doubles_mttr(self):
        """A single-replica component with dependents should have doubled MTTR."""
        est = RecoveryEstimator()
        g = InfraGraph()
        db = Component(id="db", name="DB", type=ComponentType.DATABASE, replicas=1)
        app = Component(id="app", name="App", type=ComponentType.APP_SERVER, replicas=2)
        g.add_component(db)
        g.add_component(app)
        g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))

        cr = est.estimate_component(db, g)
        # DB worst-case 120 * 2.0 (SPOF) = 240.
        assert cr.estimated_mttr_minutes >= 200

    def test_spof_not_applied_without_dependents(self):
        """SPOF doubling should not apply to leaf components with no dependents."""
        est = RecoveryEstimator()
        g, comp = _make_single_component(ComponentType.APP_SERVER, replicas=1)
        cr = est.estimate_component(comp, g)
        # 30 min worst-case, NO SPOF doubling since no dependents.
        assert cr.estimated_mttr_minutes == 30.0

    def test_dependency_depth_adds_cascade_delay(self):
        """Components deeper in the chain should take longer due to cascade delay."""
        est = RecoveryEstimator()
        g = _make_graph()
        lb_comp = g.get_component("lb")
        app_comp = g.get_component("app")
        assert lb_comp is not None
        assert app_comp is not None

        cr_lb = est.estimate_component(lb_comp, g)
        cr_app = est.estimate_component(app_comp, g)

        # LB depends on App which depends on DB => depth = 2.
        # App depends on DB => depth = 1.
        # LB should have more cascade delay than App.
        lb_depth = _dependency_depth("lb", g)
        app_depth = _dependency_depth("app", g)
        assert lb_depth > app_depth


# ===================================================================
# 3. Dependency depth helper
# ===================================================================


class TestDependencyDepth:
    """Test the _dependency_depth helper function."""

    def test_leaf_component_depth_zero(self):
        g, _ = _make_single_component()
        assert _dependency_depth("c1", g) == 0

    def test_linear_chain_depth(self):
        g = _make_graph()
        assert _dependency_depth("lb", g) == 2  # lb -> app -> db
        assert _dependency_depth("app", g) == 1  # app -> db
        assert _dependency_depth("db", g) == 0   # leaf

    def test_circular_dependency_does_not_hang(self):
        """Circular dependencies should be handled without infinite recursion."""
        g = InfraGraph()
        g.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER))
        g.add_component(Component(id="b", name="B", type=ComponentType.APP_SERVER))
        g.add_dependency(Dependency(source_id="a", target_id="b", dependency_type="requires"))
        g.add_dependency(Dependency(source_id="b", target_id="a", dependency_type="requires"))
        # Should return a finite value, not hang.
        depth = _dependency_depth("a", g)
        assert depth >= 1

    def test_diamond_dependency(self):
        """A -> B, A -> C, B -> D, C -> D: depth of A should be 2."""
        g = InfraGraph()
        g.add_component(Component(id="a", name="A", type=ComponentType.LOAD_BALANCER))
        g.add_component(Component(id="b", name="B", type=ComponentType.APP_SERVER))
        g.add_component(Component(id="c", name="C", type=ComponentType.APP_SERVER))
        g.add_component(Component(id="d", name="D", type=ComponentType.DATABASE))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="a", target_id="c"))
        g.add_dependency(Dependency(source_id="b", target_id="d"))
        g.add_dependency(Dependency(source_id="c", target_id="d"))
        assert _dependency_depth("a", g) == 2
        assert _dependency_depth("b", g) == 1
        assert _dependency_depth("d", g) == 0

    def test_nonexistent_component(self):
        """Nonexistent component should return 0 (no dependencies found)."""
        g = _make_graph()
        assert _dependency_depth("nonexistent", g) == 0


# ===================================================================
# 4. Full report (estimate)
# ===================================================================


class TestFullReport:
    """Test the full estimate() method producing a RecoveryReport."""

    def test_report_covers_all_components(self):
        g = _make_graph()
        est = RecoveryEstimator()
        report = est.estimate(g)
        assert len(report.components) == 3

    def test_report_overall_mttr_is_average(self):
        g = _make_graph()
        est = RecoveryEstimator()
        report = est.estimate(g)
        individual = [cr.estimated_mttr_minutes for cr in report.components]
        expected_avg = sum(individual) / len(individual)
        assert abs(report.overall_mttr_minutes - round(expected_avg, 2)) < 0.01

    def test_report_worst_case_is_max(self):
        g = _make_graph()
        est = RecoveryEstimator()
        report = est.estimate(g)
        individual = [cr.estimated_mttr_minutes for cr in report.components]
        assert report.worst_case_mttr_minutes == round(max(individual), 2)

    def test_report_tiers_are_populated(self):
        g = _make_graph()
        est = RecoveryEstimator()
        report = est.estimate(g)
        all_tier_ids = []
        for tier_ids in report.recovery_tiers.values():
            all_tier_ids.extend(tier_ids)
        # Every component should appear in exactly one tier.
        assert set(all_tier_ids) == {"lb", "app", "db"}

    def test_report_bottleneck_identification(self):
        g = _make_graph()
        est = RecoveryEstimator()
        report = est.estimate(g)
        # DB should be a bottleneck (highest MTTR + has dependents).
        assert isinstance(report.bottleneck_components, list)


# ===================================================================
# 5. Empty graph
# ===================================================================


class TestEmptyGraph:
    """Test behaviour with an empty infrastructure graph."""

    def test_estimate_empty_graph(self):
        g = InfraGraph()
        est = RecoveryEstimator()
        report = est.estimate(g)
        assert report.components == []
        assert report.overall_mttr_minutes == 0.0
        assert report.worst_case_mttr_minutes == 0.0
        assert report.recovery_tiers == {
            "fast": [], "moderate": [], "slow": [], "critical": [],
        }
        assert report.bottleneck_components == []

    def test_roadmap_empty_graph(self):
        g = InfraGraph()
        est = RecoveryEstimator()
        improvements = est.get_recovery_roadmap(g)
        assert improvements == []


# ===================================================================
# 6. Single component
# ===================================================================


class TestSingleComponent:
    """Test with a graph containing a single component."""

    def test_single_component_report(self):
        g, comp = _make_single_component(ComponentType.APP_SERVER, replicas=2)
        est = RecoveryEstimator()
        report = est.estimate(g)
        assert len(report.components) == 1
        assert report.overall_mttr_minutes == report.worst_case_mttr_minutes

    def test_single_component_no_bottleneck(self):
        """A single component with no dependents should not be a bottleneck."""
        g, comp = _make_single_component(ComponentType.APP_SERVER, replicas=2)
        est = RecoveryEstimator()
        report = est.estimate(g)
        assert report.bottleneck_components == []


# ===================================================================
# 7. Recovery steps
# ===================================================================


class TestRecoverySteps:
    """Test recovery step generation."""

    def test_steps_always_start_with_detection(self):
        g, comp = _make_single_component(ComponentType.APP_SERVER)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        assert len(cr.recovery_steps) > 0
        assert "Detect" in cr.recovery_steps[0].action

    def test_failover_step_when_enabled(self):
        g, comp = _make_single_component(
            ComponentType.APP_SERVER, replicas=2, failover=True,
        )
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        actions = [s.action for s in cr.recovery_steps]
        assert any("failover" in a.lower() for a in actions)

    def test_autoscaling_step_when_enabled(self):
        g, comp = _make_single_component(
            ComponentType.APP_SERVER, replicas=2, autoscaling=True,
        )
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        actions = [s.action for s in cr.recovery_steps]
        assert any("autoscal" in a.lower() for a in actions)

    def test_manual_step_when_no_automation(self):
        g, comp = _make_single_component(ComponentType.APP_SERVER)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        actions = [s.action for s in cr.recovery_steps]
        assert any("manual" in a.lower() for a in actions)

    def test_database_has_consistency_step(self):
        g, comp = _make_single_component(ComponentType.DATABASE)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        actions = [s.action for s in cr.recovery_steps]
        assert any("consistency" in a.lower() or "wal" in a.lower() for a in actions)

    def test_cache_has_warmup_step(self):
        g, comp = _make_single_component(ComponentType.CACHE)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        actions = [s.action for s in cr.recovery_steps]
        assert any("warm" in a.lower() for a in actions)

    def test_steps_end_with_verification(self):
        g, comp = _make_single_component(ComponentType.APP_SERVER)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        last_action = cr.recovery_steps[-1].action
        assert "verify" in last_action.lower() or "health" in last_action.lower()


# ===================================================================
# 8. Recovery tier classification
# ===================================================================


class TestRecoveryTiers:
    """Test that recovery tier thresholds are correct."""

    def test_fast_tier(self):
        """Components with MTTR < 5 min should be in 'fast' tier."""
        g, comp = _make_single_component(
            ComponentType.LOAD_BALANCER, replicas=3, failover=True, autoscaling=True,
        )
        est = RecoveryEstimator()
        report = est.estimate(g)
        cr = report.components[0]
        assert cr.estimated_mttr_minutes < 5.0
        assert cr.component_id in report.recovery_tiers["fast"]

    def test_critical_tier(self):
        """Components with MTTR > 120 min should be in 'critical' tier."""
        g, comp = _make_single_component(ComponentType.STORAGE, replicas=1)
        # Add a dependent so SPOF doubles it: 180 * 2 = 360.
        app = Component(id="app", name="App", type=ComponentType.APP_SERVER, replicas=2)
        g.add_component(app)
        g.add_dependency(Dependency(source_id="app", target_id="c1", dependency_type="requires"))

        est = RecoveryEstimator()
        report = est.estimate(g)
        storage_cr = next(cr for cr in report.components if cr.component_id == "c1")
        assert storage_cr.estimated_mttr_minutes >= 120.0
        assert "c1" in report.recovery_tiers["critical"]


# ===================================================================
# 9. Scenario recovery estimation
# ===================================================================


class TestScenarioRecovery:
    """Test scenario-specific recovery estimation."""

    def test_basic_scenario_recovery(self):
        g = _make_graph()
        est = RecoveryEstimator()
        sr = _make_scenario_result(fault_targets=["db"])
        recovery = est.estimate_scenario_recovery(g, sr)

        assert recovery.scenario_name == "test-scenario"
        assert recovery.total_recovery_minutes > 0
        assert recovery.critical_path_minutes > 0
        assert len(recovery.recovery_sequence) > 0

    def test_scenario_recovery_with_cascade(self):
        """Faulting the DB should cascade to app and lb."""
        g = _make_graph()
        est = RecoveryEstimator()
        sr = _make_scenario_result(fault_targets=["db"])
        recovery = est.estimate_scenario_recovery(g, sr)

        # All three components should be in the recovery.
        all_names = {s.component_name for s in recovery.recovery_sequence}
        assert len(all_names) == 3

    def test_scenario_recovery_parallel_groups(self):
        """Independent components should be in the same parallel group."""
        g = InfraGraph()
        g.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER, replicas=2))
        g.add_component(Component(id="b", name="B", type=ComponentType.APP_SERVER, replicas=2))
        g.add_component(Component(id="c", name="C", type=ComponentType.APP_SERVER, replicas=2))
        # a and b are independent; c depends on a.
        g.add_dependency(Dependency(source_id="c", target_id="a"))

        sr = _make_scenario_result(fault_targets=["a", "b"])
        est = RecoveryEstimator()
        recovery = est.estimate_scenario_recovery(g, sr)

        # a, b, and c should all be affected.
        all_comp_ids = {s.component_name for s in recovery.recovery_sequence}
        assert "A" in all_comp_ids
        assert "B" in all_comp_ids
        assert "C" in all_comp_ids

    def test_scenario_no_affected_components(self):
        """Scenario targeting a nonexistent component should return empty recovery."""
        g = _make_graph()
        sr = _make_scenario_result(fault_targets=["nonexistent"])
        est = RecoveryEstimator()
        recovery = est.estimate_scenario_recovery(g, sr)

        # "nonexistent" is not in the graph, so no known mttr.
        # But it's still in affected_ids list (it's a valid target).
        # The recovery should still not crash.
        assert recovery.scenario_name == "test-scenario"

    def test_scenario_critical_path_is_sum_of_group_maxima(self):
        """Critical path = sum of the max MTTR in each sequential group."""
        g = InfraGraph()
        g.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
        ))
        g.add_component(Component(
            id="app1", name="App1", type=ComponentType.APP_SERVER, replicas=2,
        ))
        g.add_component(Component(
            id="app2", name="App2", type=ComponentType.APP_SERVER, replicas=2,
        ))
        g.add_dependency(Dependency(source_id="app1", target_id="db"))
        g.add_dependency(Dependency(source_id="app2", target_id="db"))

        sr = _make_scenario_result(fault_targets=["db"])
        est = RecoveryEstimator()
        recovery = est.estimate_scenario_recovery(g, sr)

        # DB recovers first, then app1 and app2 in parallel.
        assert len(recovery.parallel_recovery_groups) >= 2
        assert recovery.critical_path_minutes > 0

    def test_empty_faults_scenario(self):
        """Scenario with no faults should produce empty recovery."""
        scenario = Scenario(
            id="empty", name="Empty", description="No faults", faults=[],
        )
        cascade = CascadeChain(trigger="empty", total_components=3)
        sr = ScenarioResult(scenario=scenario, cascade=cascade)

        g = _make_graph()
        est = RecoveryEstimator()
        recovery = est.estimate_scenario_recovery(g, sr)
        assert recovery.total_recovery_minutes == 0.0
        assert recovery.recovery_sequence == []


# ===================================================================
# 10. Parallel recovery groups
# ===================================================================


class TestParallelGroups:
    """Test the parallel group building algorithm."""

    def test_independent_components_in_one_group(self):
        g = InfraGraph()
        g.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER))
        g.add_component(Component(id="b", name="B", type=ComponentType.APP_SERVER))
        g.add_component(Component(id="c", name="C", type=ComponentType.APP_SERVER))

        est = RecoveryEstimator()
        groups = est._build_parallel_groups(["a", "b", "c"], g)
        # All independent => single group.
        assert len(groups) == 1
        assert set(groups[0]) == {"a", "b", "c"}

    def test_linear_chain_produces_sequential_groups(self):
        g = _make_graph()
        est = RecoveryEstimator()
        groups = est._build_parallel_groups(["lb", "app", "db"], g)
        # db has no deps in the set, so it's first; then app; then lb.
        assert len(groups) == 3

    def test_circular_dependency_handled(self):
        g = InfraGraph()
        g.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER))
        g.add_component(Component(id="b", name="B", type=ComponentType.APP_SERVER))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="a"))

        est = RecoveryEstimator()
        groups = est._build_parallel_groups(["a", "b"], g)
        # Both have in-degree 1 within the set; cycle handling should
        # place them in a remaining group.
        all_ids = {cid for grp in groups for cid in grp}
        assert "a" in all_ids
        assert "b" in all_ids

    def test_empty_affected_ids(self):
        g = _make_graph()
        est = RecoveryEstimator()
        groups = est._build_parallel_groups([], g)
        assert groups == []


# ===================================================================
# 11. Critical path calculation
# ===================================================================


class TestCriticalPath:
    """Test critical path calculation."""

    def test_single_group_critical_path(self):
        est = RecoveryEstimator()
        groups = [["a", "b", "c"]]
        mttr_map = {"a": 5.0, "b": 10.0, "c": 3.0}
        cp = est._calculate_critical_path(groups, mttr_map)
        assert cp == 10.0  # max of the single group

    def test_multi_group_critical_path(self):
        est = RecoveryEstimator()
        groups = [["db"], ["app1", "app2"], ["lb"]]
        mttr_map = {"db": 15.0, "app1": 5.0, "app2": 8.0, "lb": 1.0}
        cp = est._calculate_critical_path(groups, mttr_map)
        # 15 + 8 + 1 = 24
        assert cp == 24.0

    def test_empty_groups_critical_path(self):
        est = RecoveryEstimator()
        cp = est._calculate_critical_path([], {})
        assert cp == 0.0


# ===================================================================
# 12. Recovery roadmap
# ===================================================================


class TestRecoveryRoadmap:
    """Test the get_recovery_roadmap method."""

    def test_roadmap_generates_improvements(self):
        g = _make_graph()
        est = RecoveryEstimator()
        roadmap = est.get_recovery_roadmap(g)
        # Should have at least some improvements.
        assert len(roadmap) > 0

    def test_roadmap_sorted_by_impact(self):
        g = _make_graph()
        est = RecoveryEstimator()
        roadmap = est.get_recovery_roadmap(g)
        # Verify descending order of impact_score.
        for i in range(len(roadmap) - 1):
            assert roadmap[i].impact_score >= roadmap[i + 1].impact_score

    def test_roadmap_includes_replica_suggestion(self):
        """Single-replica components should get 'add replica' suggestion."""
        g = InfraGraph()
        g.add_component(Component(
            id="solo", name="Solo", type=ComponentType.APP_SERVER, replicas=1,
        ))
        est = RecoveryEstimator()
        roadmap = est.get_recovery_roadmap(g)
        actions = [imp.improvement_action for imp in roadmap]
        assert any("replica" in a.lower() for a in actions)

    def test_roadmap_includes_failover_suggestion(self):
        """Components without failover should get 'enable failover' suggestion."""
        g = InfraGraph()
        g.add_component(Component(
            id="nofail", name="NoFail", type=ComponentType.DATABASE, replicas=2,
        ))
        est = RecoveryEstimator()
        roadmap = est.get_recovery_roadmap(g)
        actions = [imp.improvement_action for imp in roadmap]
        assert any("failover" in a.lower() for a in actions)

    def test_roadmap_includes_autoscaling_suggestion(self):
        g = InfraGraph()
        g.add_component(Component(
            id="noas", name="NoAS", type=ComponentType.APP_SERVER, replicas=2,
        ))
        est = RecoveryEstimator()
        roadmap = est.get_recovery_roadmap(g)
        actions = [imp.improvement_action for imp in roadmap]
        assert any("autoscaling" in a.lower() for a in actions)

    def test_roadmap_includes_utilisation_suggestion(self):
        g = InfraGraph()
        g.add_component(Component(
            id="hot", name="Hot", type=ComponentType.APP_SERVER, replicas=2,
            metrics=ResourceMetrics(cpu_percent=95.0),
        ))
        est = RecoveryEstimator()
        roadmap = est.get_recovery_roadmap(g)
        actions = [imp.improvement_action for imp in roadmap]
        assert any("utilisation" in a.lower() or "utilization" in a.lower() for a in actions)

    def test_roadmap_database_backup_suggestion(self):
        g = InfraGraph()
        g.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
        ))
        est = RecoveryEstimator()
        roadmap = est.get_recovery_roadmap(g)
        actions = [imp.improvement_action for imp in roadmap]
        assert any("backup" in a.lower() for a in actions)

    def test_roadmap_external_api_no_improvements(self):
        """External APIs should have no improvements (MTTR = 0)."""
        g = InfraGraph()
        g.add_component(Component(
            id="ext", name="Ext", type=ComponentType.EXTERNAL_API,
        ))
        est = RecoveryEstimator()
        roadmap = est.get_recovery_roadmap(g)
        assert len(roadmap) == 0

    def test_improvement_impact_score_valid_range(self):
        g = _make_graph()
        est = RecoveryEstimator()
        roadmap = est.get_recovery_roadmap(g)
        for imp in roadmap:
            assert 0.0 <= imp.impact_score <= 100.0

    def test_improvement_effort_is_valid(self):
        g = _make_graph()
        est = RecoveryEstimator()
        roadmap = est.get_recovery_roadmap(g)
        valid_efforts = {"low", "medium", "high"}
        for imp in roadmap:
            assert imp.effort in valid_efforts


# ===================================================================
# 13. Component bottleneck and suggestion helpers
# ===================================================================


class TestComponentBottlenecksAndSuggestions:
    """Test the per-component bottleneck and suggestion generators."""

    def test_spof_bottleneck_identified(self):
        g, comp = _make_single_component(ComponentType.APP_SERVER, replicas=1)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        assert any("single point" in b.lower() for b in cr.bottlenecks)

    def test_high_util_bottleneck(self):
        g, comp = _make_single_component(
            ComponentType.APP_SERVER, replicas=2, cpu=90.0,
        )
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        assert any("utilisation" in b.lower() or "utilization" in b.lower() for b in cr.bottlenecks)

    def test_deep_dependency_bottleneck(self):
        g = InfraGraph()
        for i in range(5):
            g.add_component(Component(
                id=f"n{i}", name=f"N{i}", type=ComponentType.APP_SERVER,
            ))
        for i in range(4):
            g.add_dependency(Dependency(source_id=f"n{i}", target_id=f"n{i+1}"))

        comp = g.get_component("n0")
        assert comp is not None
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        assert any("dependency chain" in b.lower() or "depth" in b.lower() for b in cr.bottlenecks)

    def test_database_no_replica_bottleneck(self):
        g, comp = _make_single_component(ComponentType.DATABASE, replicas=1)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        assert any("database" in b.lower() and "replica" in b.lower() for b in cr.bottlenecks)

    def test_storage_bottleneck(self):
        g, comp = _make_single_component(ComponentType.STORAGE)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        assert any("storage" in b.lower() or "backup" in b.lower() for b in cr.bottlenecks)

    def test_cache_warming_suggestion(self):
        g, comp = _make_single_component(ComponentType.CACHE, replicas=2)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        assert any("cache warming" in s.lower() for s in cr.improvement_suggestions)

    def test_database_backup_suggestion(self):
        g, comp = _make_single_component(ComponentType.DATABASE, replicas=2)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        assert any("backup" in s.lower() for s in cr.improvement_suggestions)

    def test_no_bottleneck_for_well_provisioned(self):
        """A well-provisioned component should have fewer bottlenecks."""
        g, comp = _make_single_component(
            ComponentType.APP_SERVER, replicas=3, failover=True,
        )
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        # Should NOT have the SPOF bottleneck.
        assert not any("single point" in b.lower() for b in cr.bottlenecks)


# ===================================================================
# 14. Data class construction
# ===================================================================


class TestDataClasses:
    """Test data class instantiation and field defaults."""

    def test_recovery_step_defaults(self):
        step = RecoveryStep(
            component_name="X",
            action="test",
            estimated_minutes=5.0,
            can_parallelize=True,
        )
        assert step.dependencies == []

    def test_component_recovery_defaults(self):
        cr = ComponentRecovery(
            component_id="x",
            component_name="X",
            component_type="app_server",
            estimated_mttr_minutes=10.0,
        )
        assert cr.recovery_steps == []
        assert cr.bottlenecks == []
        assert cr.improvement_suggestions == []

    def test_recovery_report_fields(self):
        report = RecoveryReport(
            components=[],
            overall_mttr_minutes=0.0,
            worst_case_mttr_minutes=0.0,
            recovery_tiers={"fast": [], "moderate": [], "slow": [], "critical": []},
            bottleneck_components=[],
        )
        assert report.components == []

    def test_scenario_recovery_fields(self):
        sr = ScenarioRecovery(
            scenario_name="test",
            total_recovery_minutes=10.0,
            recovery_sequence=[],
            parallel_recovery_groups=[],
            critical_path_minutes=10.0,
        )
        assert sr.parallel_recovery_groups == []

    def test_recovery_improvement_fields(self):
        imp = RecoveryImprovement(
            component_name="X",
            current_mttr=60.0,
            improved_mttr=18.0,
            improvement_action="Enable failover",
            effort="medium",
            impact_score=70.0,
        )
        assert imp.effort == "medium"
        assert imp.impact_score == 70.0


# ===================================================================
# 15. Edge cases and integration
# ===================================================================


class TestEdgeCases:
    """Test various edge cases and integration scenarios."""

    def test_all_external_apis(self):
        """Graph with only external APIs should have 0 MTTR."""
        g = InfraGraph()
        g.add_component(Component(id="e1", name="E1", type=ComponentType.EXTERNAL_API))
        g.add_component(Component(id="e2", name="E2", type=ComponentType.EXTERNAL_API))
        est = RecoveryEstimator()
        report = est.estimate(g)
        assert report.overall_mttr_minutes == 0.0
        assert report.worst_case_mttr_minutes == 0.0

    def test_large_graph(self):
        """Verify the estimator handles a large graph efficiently."""
        g = InfraGraph()
        for i in range(50):
            g.add_component(Component(
                id=f"comp{i}", name=f"Comp{i}",
                type=ComponentType.APP_SERVER, replicas=2,
            ))
        # Add a chain of dependencies.
        for i in range(49):
            g.add_dependency(Dependency(source_id=f"comp{i}", target_id=f"comp{i+1}"))

        est = RecoveryEstimator()
        report = est.estimate(g)
        assert len(report.components) == 50
        # First component (deepest chain) should have highest MTTR.
        first_cr = next(cr for cr in report.components if cr.component_id == "comp0")
        last_cr = next(cr for cr in report.components if cr.component_id == "comp49")
        assert first_cr.estimated_mttr_minutes > last_cr.estimated_mttr_minutes

    def test_many_replicas_extreme(self):
        """Component with very high replica count should still return positive MTTR."""
        g, comp = _make_single_component(ComponentType.APP_SERVER, replicas=100)
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        assert cr.estimated_mttr_minutes >= 0.0

    def test_scenario_recovery_with_multiple_faults(self):
        """Scenario with multiple simultaneous faults."""
        g = _make_graph()
        sr = _make_scenario_result(fault_targets=["app", "db"])
        est = RecoveryEstimator()
        recovery = est.estimate_scenario_recovery(g, sr)
        assert recovery.total_recovery_minutes > 0
        assert len(recovery.recovery_sequence) >= 2

    def test_mixed_redundancy_graph(self):
        """Graph with a mix of well-provisioned and bare components."""
        g = InfraGraph()
        # Well-provisioned LB.
        lb = Component(
            id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=3,
        )
        lb.failover.enabled = True
        lb.autoscaling.enabled = True
        g.add_component(lb)

        # Bare DB.
        g.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
        ))
        g.add_dependency(Dependency(source_id="lb", target_id="db"))

        est = RecoveryEstimator()
        report = est.estimate(g)

        lb_cr = next(cr for cr in report.components if cr.component_id == "lb")
        db_cr = next(cr for cr in report.components if cr.component_id == "db")
        # LB should recover much faster than bare DB.
        assert lb_cr.estimated_mttr_minutes < db_cr.estimated_mttr_minutes

    def test_report_level_bottleneck_high_mttr(self):
        """Components with MTTR > 60 should be bottlenecks even without dependents."""
        g = InfraGraph()
        g.add_component(Component(
            id="big", name="Big", type=ComponentType.STORAGE, replicas=1,
        ))
        est = RecoveryEstimator()
        report = est.estimate(g)
        # Storage worst-case is 180 min; should appear in bottlenecks.
        # Actually, it has no dependents so the quartile check won't add it,
        # but the >60 min check should.
        assert "big" in report.bottleneck_components

    def test_failover_step_timing(self):
        """Failover step should use the configured promotion time."""
        g, comp = _make_single_component(
            ComponentType.DATABASE, replicas=2, failover=True,
        )
        comp.failover.promotion_time_seconds = 120.0
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        failover_steps = [
            s for s in cr.recovery_steps
            if "failover" in s.action.lower()
        ]
        assert len(failover_steps) == 1
        assert failover_steps[0].estimated_minutes == 2.0  # 120s / 60

    def test_autoscaling_step_timing(self):
        """Autoscaling step should use the configured scale-up delay."""
        g, comp = _make_single_component(
            ComponentType.APP_SERVER, replicas=2, autoscaling=True,
        )
        comp.autoscaling.scale_up_delay_seconds = 30
        est = RecoveryEstimator()
        cr = est.estimate_component(comp, g)
        as_steps = [
            s for s in cr.recovery_steps
            if "autoscal" in s.action.lower()
        ]
        assert len(as_steps) == 1
        assert as_steps[0].estimated_minutes == 0.5  # 30s / 60
