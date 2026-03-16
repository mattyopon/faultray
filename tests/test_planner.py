"""Tests for the Remediation Planner."""

from __future__ import annotations

import math

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    RegionConfig,
    ResourceMetrics,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.planner import (
    TASK_ESTIMATES,
    PlanTask,
    RemediationPhase,
    RemediationPlan,
    RemediationPlanner,
)


# ---------------------------------------------------------------------------
# Helper: build test graphs
# ---------------------------------------------------------------------------


def _build_weak_graph() -> InfraGraph:
    """Build a graph with many weaknesses (no redundancy, no security, no DR)."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb",
        name="Load Balancer",
        type=ComponentType.LOAD_BALANCER,
        port=443,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=20, memory_percent=30),
    ))
    graph.add_component(Component(
        id="app",
        name="API Server",
        type=ComponentType.APP_SERVER,
        port=8080,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=50, memory_percent=60),
    ))
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=40, memory_percent=70),
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


def _build_strong_graph() -> InfraGraph:
    """Build a well-configured graph (replicas, failover, autoscaling, security, CB)."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb",
        name="Load Balancer",
        type=ComponentType.LOAD_BALANCER,
        port=443,
        replicas=2,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
        failover=FailoverConfig(enabled=True),
        security=SecurityProfile(
            encryption_at_rest=True, encryption_in_transit=True,
            waf_protected=True, network_segmented=True,
            backup_enabled=True,
        ),
        region=RegionConfig(dr_target_region="us-west-2"),
    ))
    graph.add_component(Component(
        id="app",
        name="API Server",
        type=ComponentType.APP_SERVER,
        port=8080,
        replicas=3,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=6),
        failover=FailoverConfig(enabled=True),
        security=SecurityProfile(
            encryption_at_rest=True, encryption_in_transit=True,
            waf_protected=True, network_segmented=True,
            backup_enabled=True,
        ),
    ))
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=2,
        failover=FailoverConfig(enabled=True),
        security=SecurityProfile(
            encryption_at_rest=True, encryption_in_transit=True,
            network_segmented=True,
            backup_enabled=True,
        ),
        region=RegionConfig(dr_target_region="us-west-2"),
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    return graph


def _build_single_component_graph() -> InfraGraph:
    """Build a graph with a single component."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app",
        name="App",
        type=ComponentType.APP_SERVER,
        replicas=1,
    ))
    return graph


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPlanTask:
    """Tests for PlanTask data model."""

    def test_roi_percent_positive_cost(self):
        """ROI should be calculated correctly when cost is positive."""
        task = PlanTask(
            id="1.1", title="Test", description="", phase=1,
            category="redundancy", priority="high",
            required_role="SRE", estimated_hours=10,
            monthly_cost_increase=100, one_time_cost=500,
            resilience_score_delta=5.0,
            risk_reduction_annual=5000.0,
        )
        # annual_cost = 100*12 + 500 = 1700
        # roi = (5000 - 1700) / 1700 * 100
        expected = (5000 - 1700) / 1700 * 100
        assert abs(task.roi_percent - expected) < 0.01

    def test_roi_percent_zero_cost(self):
        """ROI should be infinite when cost is zero and benefit is positive."""
        task = PlanTask(
            id="1.1", title="Test", description="", phase=1,
            category="redundancy", priority="high",
            required_role="SRE", estimated_hours=0,
            monthly_cost_increase=0, one_time_cost=0,
            resilience_score_delta=3.0,
            risk_reduction_annual=5000.0,
        )
        assert task.roi_percent == float("inf")

    def test_roi_percent_zero_benefit_zero_cost(self):
        """ROI should be 0 when both cost and benefit are zero."""
        task = PlanTask(
            id="1.1", title="Test", description="", phase=1,
            category="redundancy", priority="high",
            required_role="SRE", estimated_hours=0,
            monthly_cost_increase=0, one_time_cost=0,
            resilience_score_delta=0.0,
            risk_reduction_annual=0.0,
        )
        assert task.roi_percent == 0.0


class TestRemediationPlan:
    """Tests for RemediationPlan data model."""

    def test_summary_property(self):
        """Plan summary should contain key information."""
        plan = RemediationPlan(
            current_score=45.0,
            target_score=90.0,
            phases=[
                RemediationPhase(
                    phase_number=1,
                    name="Critical Fixes",
                    tasks=[PlanTask(
                        id="1.1", title="Add replica", description="desc",
                        phase=1, category="redundancy", priority="critical",
                        required_role="DBA", estimated_hours=8,
                        monthly_cost_increase=800, one_time_cost=1200,
                        resilience_score_delta=5.0,
                        risk_reduction_annual=50000,
                    )],
                    estimated_weeks=2,
                    team_size=3,
                    phase_cost=10800,
                    score_before=45.0,
                    score_after=50.0,
                ),
            ],
            total_weeks=2,
            total_budget=10800,
            total_risk_reduction=50000,
            overall_roi=363.0,
        )
        summary = plan.summary
        assert "45.0" in summary
        assert "90.0" in summary
        assert "2 weeks" in summary
        assert "Critical Fixes" in summary
        assert "Add replica" in summary


class TestRemediationPlanner:
    """Tests for the RemediationPlanner engine."""

    def test_plan_weak_graph_produces_tasks(self):
        """A weak graph should produce multiple remediation tasks."""
        graph = _build_weak_graph()
        planner = RemediationPlanner(graph)
        plan = planner.plan(target_score=90.0)

        assert plan.current_score >= 0
        assert len(plan.phases) > 0
        total_tasks = sum(len(p.tasks) for p in plan.phases)
        assert total_tasks > 0

    def test_plan_strong_graph_fewer_tasks(self):
        """A well-configured graph should produce fewer tasks."""
        weak_graph = _build_weak_graph()
        strong_graph = _build_strong_graph()

        weak_planner = RemediationPlanner(weak_graph)
        strong_planner = RemediationPlanner(strong_graph)

        weak_plan = weak_planner.plan()
        strong_plan = strong_planner.plan()

        weak_tasks = sum(len(p.tasks) for p in weak_plan.phases)
        strong_tasks = sum(len(p.tasks) for p in strong_plan.phases)

        assert strong_tasks < weak_tasks

    def test_plan_phases_have_correct_numbers(self):
        """Phase numbers should be 1, 2, or 3."""
        graph = _build_weak_graph()
        planner = RemediationPlanner(graph)
        plan = planner.plan()

        for phase in plan.phases:
            assert phase.phase_number in (1, 2, 3)

    def test_plan_phase_ordering(self):
        """Phases should be in ascending order."""
        graph = _build_weak_graph()
        planner = RemediationPlanner(graph)
        plan = planner.plan()

        phase_numbers = [p.phase_number for p in plan.phases]
        assert phase_numbers == sorted(phase_numbers)

    def test_plan_task_ids_are_assigned(self):
        """Each task should have a proper ID like '1.1', '2.3', etc."""
        graph = _build_weak_graph()
        planner = RemediationPlanner(graph)
        plan = planner.plan()

        for phase in plan.phases:
            for task in phase.tasks:
                assert task.id != ""
                parts = task.id.split(".")
                assert len(parts) == 2
                assert parts[0] == str(phase.phase_number)
                assert int(parts[1]) >= 1

    def test_plan_budget_limit_constrains_tasks(self):
        """Setting a budget limit should constrain the number of tasks."""
        graph = _build_weak_graph()
        planner = RemediationPlanner(graph)

        unlimited_plan = planner.plan()
        limited_plan = planner.plan(budget_limit=5000)

        unlimited_tasks = sum(len(p.tasks) for p in unlimited_plan.phases)
        limited_tasks = sum(len(p.tasks) for p in limited_plan.phases)

        assert limited_tasks <= unlimited_tasks
        assert limited_plan.total_budget <= 5000 or limited_tasks == 0

    def test_plan_budget_limit_zero(self):
        """Budget of zero should produce no tasks."""
        graph = _build_weak_graph()
        planner = RemediationPlanner(graph)
        plan = planner.plan(budget_limit=0)

        total_tasks = sum(len(p.tasks) for p in plan.phases)
        assert total_tasks == 0

    def test_plan_single_component(self):
        """Planner should handle a single component gracefully."""
        graph = _build_single_component_graph()
        planner = RemediationPlanner(graph)
        plan = planner.plan()

        # Should not crash and produce some plan
        assert plan.current_score >= 0
        assert isinstance(plan.phases, list)

    def test_plan_empty_graph(self):
        """Planner should handle an empty graph."""
        graph = InfraGraph()
        planner = RemediationPlanner(graph)
        plan = planner.plan()

        assert plan.current_score == 0.0
        total_tasks = sum(len(p.tasks) for p in plan.phases)
        assert total_tasks == 0

    def test_plan_to_dict_serializable(self):
        """plan_to_dict should produce a JSON-serializable dict."""
        import json

        graph = _build_weak_graph()
        planner = RemediationPlanner(graph)
        plan = planner.plan()
        d = planner.plan_to_dict(plan)

        # Should be JSON serializable
        json_str = json.dumps(d, default=str)
        assert json_str is not None

        # Key structure
        assert "current_score" in d
        assert "target_score" in d
        assert "phases" in d
        assert "summary" in d
        assert isinstance(d["phases"], list)

    def test_plan_dr_tasks_depend_on_replica_tasks(self):
        """DR tasks should depend on replica/failover tasks from phase 1."""
        graph = _build_weak_graph()
        planner = RemediationPlanner(graph)
        plan = planner.plan()

        # Find phase 3 tasks (DR)
        for phase in plan.phases:
            if phase.phase_number == 3:
                for task in phase.tasks:
                    if task.category == "dr":
                        # If there are phase 1 replica tasks, depends_on should
                        # reference them
                        phase1_tasks = [
                            p.tasks for p in plan.phases if p.phase_number == 1
                        ]
                        if phase1_tasks and phase1_tasks[0]:
                            replica_ids = [
                                t.id for t in phase1_tasks[0]
                                if "replica" in t.title.lower()
                                or "failover" in t.title.lower()
                            ]
                            if replica_ids:
                                assert len(task.depends_on) > 0

    def test_plan_score_progression(self):
        """Each phase's score_after should be >= score_before."""
        graph = _build_weak_graph()
        planner = RemediationPlanner(graph)
        plan = planner.plan()

        for phase in plan.phases:
            assert phase.score_after >= phase.score_before

    def test_plan_total_weeks_matches_phases(self):
        """Total weeks should be the sum of phase estimated weeks."""
        graph = _build_weak_graph()
        planner = RemediationPlanner(graph)
        plan = planner.plan()

        expected_weeks = sum(p.estimated_weeks for p in plan.phases)
        assert plan.total_weeks == expected_weeks

    def test_plan_tasks_have_valid_categories(self):
        """All tasks should have valid categories."""
        valid_categories = {"redundancy", "security", "dr", "monitoring", "compliance"}
        graph = _build_weak_graph()
        planner = RemediationPlanner(graph)
        plan = planner.plan()

        for phase in plan.phases:
            for task in phase.tasks:
                assert task.category in valid_categories

    def test_plan_tasks_have_valid_priorities(self):
        """All tasks should have valid priorities."""
        valid_priorities = {"critical", "high", "medium", "low"}
        graph = _build_weak_graph()
        planner = RemediationPlanner(graph)
        plan = planner.plan()

        for phase in plan.phases:
            for task in phase.tasks:
                assert task.priority in valid_priorities

    def test_task_estimates_keys_exist(self):
        """TASK_ESTIMATES should have all expected keys."""
        expected_actions = {
            "add_replica", "enable_autoscaling", "add_waf",
            "enable_encryption", "setup_dr", "add_monitoring",
            "network_segmentation", "add_backup",
            "add_circuit_breaker", "add_failover",
        }
        assert set(TASK_ESTIMATES.keys()) == expected_actions

    def test_extract_component_id(self):
        """_extract_component_id should extract IDs from recommendation strings."""
        planner = RemediationPlanner(InfraGraph())
        assert planner._extract_component_id("Component 'app-1' has no redundancy") == "app-1"
        assert planner._extract_component_id("No component id here") == ""
        assert planner._extract_component_id("component 'db' is slow") == "db"

    def test_high_utilization_recommendation_generates_task(self):
        """A 'high utilization' recommendation should generate an autoscaling task."""
        graph = _build_single_component_graph()
        planner = RemediationPlanner(graph)
        tasks = planner._generate_tasks_from_recommendations(
            ["Component 'app' has high utilization (cpu > 80%)"]
        )
        assert len(tasks) == 1
        assert "autoscaling" in tasks[0].title.lower() or "scale up" in tasks[0].title.lower()
        assert tasks[0].priority == "high"
        assert "'app'" in tasks[0].title

    def test_high_utilization_recommendation_without_component_id(self):
        """A 'high utilization' recommendation without component ID uses fallback title."""
        graph = _build_single_component_graph()
        planner = RemediationPlanner(graph)
        tasks = planner._generate_tasks_from_recommendations(
            ["Warning: high utilization detected"]
        )
        assert len(tasks) == 1
        assert tasks[0].title == "Address high utilization"

    def test_task_with_unknown_phase_falls_back_to_phase3(self):
        """Tasks with a phase not in {1, 2, 3} should be grouped into phase 3."""
        graph = _build_weak_graph()
        planner = RemediationPlanner(graph)

        # Monkey-patch _generate_tasks_from_recommendations to return a task
        # with phase=99, which is not in the phase_groups dict {1, 2, 3}.
        original_method = planner._generate_tasks_from_recommendations

        def patched_method(recommendations):
            tasks = original_method(recommendations)
            # Add a task with an invalid phase number
            tasks.append(PlanTask(
                id="",
                title="Custom task with unknown phase",
                description="Task with phase outside {1, 2, 3}",
                phase=99,
                category="redundancy",
                priority="medium",
                required_role="SRE",
                estimated_hours=4,
                monthly_cost_increase=0,
                one_time_cost=600,
                resilience_score_delta=2.0,
                risk_reduction_annual=10000.0,
            ))
            return tasks

        planner._generate_tasks_from_recommendations = patched_method
        plan = planner.plan()

        # The task with phase=99 should end up in phase 3
        phase3 = [p for p in plan.phases if p.phase_number == 3]
        assert len(phase3) > 0
        phase3_titles = [t.title for t in phase3[0].tasks]
        assert "Custom task with unknown phase" in phase3_titles

    def test_estimate_score_delta_scales_for_large_graphs(self):
        """Score delta should be scaled down for graphs with > 5 components."""
        graph = InfraGraph()
        # Add 6 components to trigger the n > 5 branch
        for i in range(6):
            graph.add_component(Component(
                id=f"comp-{i}",
                name=f"Component {i}",
                type=ComponentType.APP_SERVER,
                replicas=1,
            ))
        planner = RemediationPlanner(graph)

        # For 6 components: delta = base_delta * 5 / 6
        delta = planner._estimate_score_delta("add_replica")
        # base for add_replica is 5.0, scaled: 5.0 * 5/6 = ~4.17 -> rounded to 4.2
        expected = round(5.0 * 5 / 6, 1)
        assert delta == expected

        # Compare with a small graph (<=5 components) - no scaling
        small_graph = _build_single_component_graph()
        small_planner = RemediationPlanner(small_graph)
        small_delta = small_planner._estimate_score_delta("add_replica")
        assert small_delta == 5.0
        assert delta < small_delta
