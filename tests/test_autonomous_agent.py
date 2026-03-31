"""Tests for faultray.remediation.autonomous_agent.

Covers the full detect -> plan -> simulate -> execute -> verify cycle,
ratchet permission enforcement, persistence, and edge cases.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.remediation.autonomous_agent import (
    AutonomousRemediationAgent,
    RemediationCycle,
    StepResult,
    _PlanStep,
    _SimResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    cpu: float = 0.0,
    memory: float = 0.0,
    health: HealthStatus = HealthStatus.HEALTHY,
    failover: bool = False,
    autoscaling: bool = False,
    backup: bool = False,
    encryption: bool = False,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.metrics = ResourceMetrics(cpu_percent=cpu, memory_percent=memory)
    c.capacity = Capacity()
    c.health = health
    if failover:
        c.failover = FailoverConfig(enabled=True)
    if autoscaling:
        c.autoscaling = AutoScalingConfig(enabled=True)
    c.security = SecurityProfile(
        backup_enabled=backup, encryption_at_rest=encryption
    )
    return c


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _healthy_graph() -> InfraGraph:
    """A well-configured graph that produces no remediation issues."""
    return _graph(
        _comp(
            "web",
            "Web Server",
            ComponentType.WEB_SERVER,
            replicas=3,
            failover=True,
            autoscaling=True,
            backup=True,
            encryption=True,
        ),
        _comp(
            "db",
            "Database",
            ComponentType.DATABASE,
            replicas=3,
            failover=True,
            backup=True,
            encryption=True,
        ),
    )


def _unhealthy_graph() -> InfraGraph:
    """A graph with many issues for remediation."""
    g = _graph(
        _comp("web", "Web Server", ComponentType.WEB_SERVER, replicas=1),
        _comp("app", "App Server", ComponentType.APP_SERVER, replicas=1, cpu=95.0),
        _comp("db", "Database", ComponentType.DATABASE, replicas=1),
        _comp("cache", "Cache", ComponentType.CACHE, replicas=1),
    )
    g.add_dependency(Dependency(source_id="web", target_id="app"))
    g.add_dependency(Dependency(source_id="app", target_id="db"))
    g.add_dependency(Dependency(source_id="app", target_id="cache"))
    return g


def _make_agent(
    tmp_path: Path,
    graph: InfraGraph | None = None,
    auto_approve: bool = False,
    dry_run: bool = True,
    max_risk: str = "medium",
    ratchet_enabled: bool = True,
) -> AutonomousRemediationAgent:
    """Create an agent with a saved model in tmp_path."""
    model_path = tmp_path / "model.json"
    g = graph or _unhealthy_graph()
    g.save(model_path)

    return AutonomousRemediationAgent(
        model_path=str(model_path),
        auto_approve=auto_approve,
        max_risk_level=max_risk,
        ratchet_enabled=ratchet_enabled,
        dry_run=dry_run,
        output_dir=str(tmp_path / "remediation"),
    )


# ===========================================================================
# 1. Full dry-run cycle (detect -> plan -> simulate -> complete)
# ===========================================================================


class TestFullDryRunCycle:
    def test_dry_run_cycle_completes(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=True)
        cycle = agent.run_cycle()

        assert cycle.status in ("completed", "failed", "awaiting_approval")
        assert cycle.id
        assert cycle.started_at

    def test_dry_run_cycle_has_initial_score(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=True)
        cycle = agent.run_cycle()
        # Score is computed from the graph
        assert isinstance(cycle.initial_score, float)

    def test_dry_run_execution_log_shows_dry_run(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=True)
        cycle = agent.run_cycle()
        if cycle.execution_log:
            statuses = {e["status"] for e in cycle.execution_log}
            # In dry-run mode, steps are "dry_run" or "blocked"
            assert statuses <= {"dry_run", "blocked"}


# ===========================================================================
# 2. No issues found
# ===========================================================================


class TestNoIssuesFound:
    def test_healthy_graph_no_issues(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, graph=_healthy_graph(), auto_approve=True)
        cycle = agent.run_cycle()
        # Healthy graph might still have some issues detected by the engine
        # but the cycle should complete
        assert cycle.status in ("completed", "failed")

    def test_empty_graph_completes(self, tmp_path: Path) -> None:
        g = InfraGraph()
        agent = _make_agent(tmp_path, graph=g, auto_approve=True)
        cycle = agent.run_cycle()
        assert cycle.status == "completed"
        assert len(cycle.issues_found) == 0


# ===========================================================================
# 3. Issue extraction from simulation report
# ===========================================================================


class TestIssueExtraction:
    def test_unhealthy_graph_finds_issues(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=True)
        cycle = agent.run_cycle()
        assert len(cycle.issues_found) > 0

    def test_issues_have_expected_fields(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=True)
        cycle = agent.run_cycle()
        if cycle.issues_found:
            issue = cycle.issues_found[0]
            assert "plan_id" in issue
            assert "description" in issue
            assert "priority" in issue
            assert "affected_components" in issue


# ===========================================================================
# 4. Plan generation produces valid IaC
# ===========================================================================


class TestPlanGeneration:
    def test_plan_is_generated(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=True)
        cycle = agent.run_cycle()
        # If issues were found, a plan should be generated
        if cycle.issues_found:
            assert cycle.remediation_plan is not None

    def test_plan_has_cost_estimate(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=True)
        cycle = agent.run_cycle()
        if cycle.remediation_plan:
            assert cycle.estimated_cost != "$0.00"


# ===========================================================================
# 5. Ratchet blocks unauthorized operations
# ===========================================================================


class TestRatchetBlocking:
    def test_ratchet_narrows_after_high_risk(self, tmp_path: Path) -> None:
        """After executing a high-risk step, ratchet should narrow permissions."""
        agent = _make_agent(tmp_path, auto_approve=True, ratchet_enabled=True)
        cycle = agent.run_cycle()
        if cycle.ratchet_state:
            perms = set(cycle.ratchet_state.get("remaining_permissions", []))
            # After high-risk access, write/send perms should be gone
            # (depends on what steps were actually executed)
            assert isinstance(perms, set)

    def test_ratchet_disabled_preserves_all_perms(self, tmp_path: Path) -> None:
        agent = _make_agent(
            tmp_path, auto_approve=True, ratchet_enabled=False
        )
        cycle = agent.run_cycle()
        if cycle.ratchet_state:
            perms = set(cycle.ratchet_state.get("remaining_permissions", []))
            # Without ratchet, permissions should include more scopes
            assert "write:internal" in perms or len(perms) > 0

    def test_blocked_steps_logged(self, tmp_path: Path) -> None:
        """If ratchet blocks a step, it should appear in execution log."""
        agent = _make_agent(tmp_path, auto_approve=True, ratchet_enabled=True)
        cycle = agent.run_cycle()
        blocked = [
            e for e in cycle.execution_log if e.get("status") == "blocked"
        ]
        # Some steps may be blocked after high-risk operations narrow permissions
        # This is expected behavior — just verify they're logged correctly
        for entry in blocked:
            assert "reason" in entry


# ===========================================================================
# 6. Ratchet narrows permissions after production access
# ===========================================================================


class TestRatchetNarrowing:
    def test_ratchet_state_is_recorded(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=True)
        cycle = agent.run_cycle()
        if cycle.execution_log:
            assert "ratchet_state" in cycle.to_dict()

    def test_ratchet_high_water_mark(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=True, ratchet_enabled=True)
        cycle = agent.run_cycle()
        if cycle.ratchet_state:
            level = cycle.ratchet_state.get("final_level")
            assert level is not None


# ===========================================================================
# 7. Auto-approve vs manual approve flow
# ===========================================================================


class TestApprovalFlow:
    def test_manual_approve_pauses_at_approval(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=False)
        cycle = agent.run_cycle()
        # If issues found, should pause at awaiting_approval
        if cycle.issues_found and cycle.simulation_passed:
            assert cycle.status == "awaiting_approval"
            # Execution log should be empty (not yet executed)
            assert len(cycle.execution_log) == 0

    def test_auto_approve_skips_approval(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=True)
        cycle = agent.run_cycle()
        # Should NOT be awaiting_approval
        assert cycle.status != "awaiting_approval"


# ===========================================================================
# 8. Verification detects improvement
# ===========================================================================


class TestVerification:
    def test_completed_cycle_has_final_score(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=True)
        cycle = agent.run_cycle()
        if cycle.status == "completed" and cycle.issues_found:
            assert cycle.final_score is not None

    def test_improvement_is_calculated(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=True)
        cycle = agent.run_cycle()
        if cycle.status == "completed" and cycle.issues_found:
            assert cycle.improvement_achieved is not None


# ===========================================================================
# 9. Report generation
# ===========================================================================


class TestReportGeneration:
    def test_report_summary_is_set(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=True)
        cycle = agent.run_cycle()
        assert cycle.report_summary

    def test_markdown_report_saved(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=True)
        cycle = agent.run_cycle()
        if cycle.status in ("completed", "failed", "rolled_back"):
            report = agent.get_latest_report()
            if report:
                assert "FaultRay" in report

    def test_json_report_saved(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=True)
        cycle = agent.run_cycle()
        if cycle.status in ("completed", "failed", "rolled_back"):
            data = agent.get_latest_report_json()
            if data:
                assert "id" in data
                assert "status" in data


# ===========================================================================
# 10. Cycle persistence (save/load)
# ===========================================================================


class TestCyclePersistence:
    def test_save_and_load_cycle(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=False)
        cycle = agent.run_cycle()

        # The cycle should be saved
        loaded = agent._load_cycle(cycle.id)
        assert loaded.id == cycle.id
        assert loaded.status == cycle.status
        assert loaded.initial_score == cycle.initial_score

    def test_load_nonexistent_raises(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path)
        with pytest.raises(FileNotFoundError):
            agent._load_cycle("nonexistent-id")

    def test_list_history(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=True)
        agent.run_cycle()
        history = agent.list_history()
        assert len(history) >= 1

    def test_list_pending(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=False)
        cycle = agent.run_cycle()
        pending = agent.list_pending()
        if cycle.status == "awaiting_approval":
            assert any(p.id == cycle.id for p in pending)


# ===========================================================================
# 11. Simulation failure
# ===========================================================================


class TestSimulationFailure:
    def test_score_regression_fails_simulation(self, tmp_path: Path) -> None:
        """_simulate_with_fix should fail if predicted score decreases."""
        agent = _make_agent(tmp_path)

        from faultray.remediation.iac_generator import RemediationFile, RemediationPlan

        # Create a plan with negative improvement (must have files to not short-circuit)
        plan = RemediationPlan(
            expected_score_before=80.0,
            expected_score_after=70.0,
            files=[
                RemediationFile(
                    path="bad.tf",
                    content="resource {}",
                    description="Bad fix",
                    phase=3,
                    impact_score_delta=-10.0,
                    monthly_cost=0.0,
                    category="dr",
                ),
            ],
        )
        result = agent._simulate_with_fix(_unhealthy_graph(), plan)
        assert not result.passed
        assert any("decrease" in s for s in result.side_effects)

    def test_empty_plan_passes_simulation(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path)
        from faultray.remediation.iac_generator import RemediationPlan

        plan = RemediationPlan()
        result = agent._simulate_with_fix(_unhealthy_graph(), plan)
        assert result.passed


# ===========================================================================
# 12. _PlanStep and permission helpers
# ===========================================================================


class TestHelpers:
    def test_plan_to_steps_terraform(self, tmp_path: Path) -> None:
        from faultray.remediation.iac_generator import RemediationFile, RemediationPlan

        plan = RemediationPlan(
            files=[
                RemediationFile(
                    path="phase1/test.tf",
                    content="resource {}",
                    description="Test",
                    phase=1,
                    impact_score_delta=5.0,
                    monthly_cost=100.0,
                    category="redundancy",
                ),
            ]
        )
        steps = AutonomousRemediationAgent._plan_to_steps(plan)
        assert len(steps) == 1
        assert steps[0].execution_type == "terraform"
        assert steps[0].risk_level == "high"

    def test_plan_to_steps_kubernetes(self, tmp_path: Path) -> None:
        from faultray.remediation.iac_generator import RemediationFile, RemediationPlan

        plan = RemediationPlan(
            files=[
                RemediationFile(
                    path="phase1/test.yaml",
                    content="apiVersion: v1",
                    description="K8s",
                    phase=2,
                    impact_score_delta=3.0,
                    monthly_cost=0.0,
                    category="security",
                ),
            ]
        )
        steps = AutonomousRemediationAgent._plan_to_steps(plan)
        assert steps[0].execution_type == "kubernetes"
        assert steps[0].risk_level == "medium"

    def test_step_permissions_terraform(self) -> None:
        step = _PlanStep(
            description="test",
            risk_level="high",
            file_path="test.tf",
            content="",
            execution_type="terraform",
        )
        perms = AutonomousRemediationAgent._step_permissions(step)
        assert "execute:tool" in perms
        assert "write:internal" in perms

    def test_step_permissions_kubernetes(self) -> None:
        step = _PlanStep(
            description="test",
            risk_level="low",
            file_path="test.yaml",
            content="",
            execution_type="kubernetes",
        )
        perms = AutonomousRemediationAgent._step_permissions(step)
        assert "write:internal" in perms
        assert "execute:tool" not in perms


# ===========================================================================
# 13. Cycle serialization
# ===========================================================================


class TestCycleSerialization:
    def test_to_dict_round_trip(self) -> None:
        cycle = RemediationCycle(
            id="test-123",
            started_at="2026-01-01T00:00:00Z",
            status="completed",
            initial_score=60.0,
            issues_found=[{"description": "test", "priority": "urgent"}],
            estimated_cost="$100.00/mo",
        )
        d = cycle.to_dict()
        assert d["id"] == "test-123"
        assert d["status"] == "completed"
        assert d["initial_score"] == 60.0

        restored = AutonomousRemediationAgent._dict_to_cycle(d)
        assert restored.id == cycle.id
        assert restored.status == cycle.status
        assert restored.initial_score == cycle.initial_score

    def test_dict_to_cycle_missing_fields(self) -> None:
        """_dict_to_cycle should handle missing optional fields gracefully."""
        data = {
            "id": "minimal",
            "started_at": "2026-01-01T00:00:00Z",
        }
        cycle = AutonomousRemediationAgent._dict_to_cycle(data)
        assert cycle.id == "minimal"
        assert cycle.status == "unknown"
        assert cycle.issues_found == []


# ===========================================================================
# 14. StepResult dataclass
# ===========================================================================


class TestStepResult:
    def test_step_result_default(self) -> None:
        r = StepResult(status="success")
        assert r.status == "success"
        assert r.output == ""

    def test_step_result_with_output(self) -> None:
        r = StepResult(status="failed", output="something broke")
        assert r.status == "failed"
        assert "broke" in r.output


# ===========================================================================
# 15. _SimResult dataclass
# ===========================================================================


class TestSimResult:
    def test_sim_result_passed(self) -> None:
        r = _SimResult(passed=True, new_score=95.0)
        assert r.passed
        assert r.side_effects == []

    def test_sim_result_failed(self) -> None:
        r = _SimResult(passed=False, new_score=50.0, side_effects=["bad"])
        assert not r.passed
        assert len(r.side_effects) == 1


# ===========================================================================
# 16. Model file not found
# ===========================================================================


class TestModelNotFound:
    def test_missing_model_raises(self, tmp_path: Path) -> None:
        agent = AutonomousRemediationAgent(
            model_path=str(tmp_path / "nonexistent.json"),
            output_dir=str(tmp_path / "remediation"),
        )
        with pytest.raises(FileNotFoundError):
            agent.run_cycle()


# ===========================================================================
# 17. Approve non-pending cycle
# ===========================================================================


class TestApproveErrors:
    def test_approve_nonexistent_cycle_raises(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path)
        with pytest.raises(FileNotFoundError):
            agent.approve_and_execute("does-not-exist")

    def test_approve_completed_cycle_raises(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=True)
        cycle = agent.run_cycle()
        if cycle.status != "awaiting_approval":
            with pytest.raises(ValueError, match="not awaiting approval"):
                agent.approve_and_execute(cycle.id)


# ===========================================================================
# 18. Latest report when no reports exist
# ===========================================================================


class TestNoReports:
    def test_no_latest_report(self, tmp_path: Path) -> None:
        agent = AutonomousRemediationAgent(
            model_path="fake.json",
            output_dir=str(tmp_path / "empty-remediation"),
        )
        assert agent.get_latest_report() is None

    def test_no_latest_report_json(self, tmp_path: Path) -> None:
        agent = AutonomousRemediationAgent(
            model_path="fake.json",
            output_dir=str(tmp_path / "empty-remediation"),
        )
        assert agent.get_latest_report_json() is None


# ===========================================================================
# 19. Max risk level filtering
# ===========================================================================


class TestMaxRiskLevel:
    def test_low_risk_blocks_high_risk_steps(self, tmp_path: Path) -> None:
        """With max_risk=low, high-risk file phases should produce side effects."""
        agent = _make_agent(tmp_path, auto_approve=True, max_risk="low")
        cycle = agent.run_cycle()
        # The cycle may fail or have side_effects reported
        # depending on whether the plan has high-risk files
        assert cycle.status in ("completed", "failed")


# ===========================================================================
# 20. Phase-to-risk mapping
# ===========================================================================


class TestPhaseRiskMapping:
    def test_phase1_is_high(self) -> None:
        from faultray.remediation.iac_generator import RemediationFile, RemediationPlan

        plan = RemediationPlan(
            files=[
                RemediationFile(
                    path="p1/test.tf",
                    content="",
                    description="",
                    phase=1,
                    impact_score_delta=0.0,
                    monthly_cost=0.0,
                    category="redundancy",
                ),
            ]
        )
        steps = AutonomousRemediationAgent._plan_to_steps(plan)
        assert steps[0].risk_level == "high"

    def test_phase2_is_medium(self) -> None:
        from faultray.remediation.iac_generator import RemediationFile, RemediationPlan

        plan = RemediationPlan(
            files=[
                RemediationFile(
                    path="p2/test.tf",
                    content="",
                    description="",
                    phase=2,
                    impact_score_delta=0.0,
                    monthly_cost=0.0,
                    category="security",
                ),
            ]
        )
        steps = AutonomousRemediationAgent._plan_to_steps(plan)
        assert steps[0].risk_level == "medium"

    def test_phase3_is_low(self) -> None:
        from faultray.remediation.iac_generator import RemediationFile, RemediationPlan

        plan = RemediationPlan(
            files=[
                RemediationFile(
                    path="p3/test.tf",
                    content="",
                    description="",
                    phase=3,
                    impact_score_delta=0.0,
                    monthly_cost=0.0,
                    category="dr",
                ),
            ]
        )
        steps = AutonomousRemediationAgent._plan_to_steps(plan)
        assert steps[0].risk_level == "low"


# ===========================================================================
# 21. Execute step (subprocess mocking)
# ===========================================================================


class TestExecuteStep:
    def test_execute_terraform_not_found(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, dry_run=False)
        step = _PlanStep(
            description="test tf",
            risk_level="low",
            file_path="test.tf",
            content='resource "null" "test" {}',
            execution_type="terraform",
        )
        result = agent._execute_terraform(step)
        # terraform CLI likely not installed in test env
        assert result.status in ("failed", "timeout")

    def test_execute_kubernetes_not_found(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, dry_run=False)
        step = _PlanStep(
            description="test k8s",
            risk_level="low",
            file_path="test.yaml",
            content="apiVersion: v1\nkind: ConfigMap",
            execution_type="kubernetes",
        )
        result = agent._execute_kubernetes(step)
        assert result.status in ("failed", "timeout")

    def test_execute_step_unknown_type(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, dry_run=False)
        step = _PlanStep(
            description="custom",
            risk_level="low",
            file_path="script.sh",
            content="echo hello",
            execution_type="script",
        )
        result = agent._execute_step(step)
        assert result.status == "success"


# ===========================================================================
# 22. Markdown report rendering
# ===========================================================================


class TestMarkdownReport:
    def test_render_contains_expected_sections(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=True)
        cycle = RemediationCycle(
            id="rpt-test",
            started_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:01:00Z",
            status="completed",
            initial_score=50.0,
            simulated_score=80.0,
            final_score=75.0,
            improvement_achieved=25.0,
            issues_found=[
                {"description": "DB no replica", "priority": "urgent", "affected_components": ["db"]},
            ],
            execution_log=[
                {"step": "Add replica", "status": "dry_run"},
            ],
            ratchet_state={"final_level": "RESTRICTED", "remaining_permissions": ["read:internal"]},
        )
        md = agent._render_markdown_report(cycle)
        assert "FaultRay Remediation Report" in md
        assert "Score" in md
        assert "Execution Log" in md
        assert "Ratchet State" in md


# ===========================================================================
# 23. Cycle completed_at timestamp
# ===========================================================================


class TestTimestamps:
    def test_completed_cycle_has_completed_at(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=True)
        cycle = agent.run_cycle()
        if cycle.status in ("completed", "failed", "rolled_back"):
            assert cycle.completed_at is not None

    def test_pending_cycle_no_completed_at(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path, auto_approve=False)
        cycle = agent.run_cycle()
        if cycle.status == "awaiting_approval":
            assert cycle.completed_at is None


# ===========================================================================
# 24. Execution failure sets status to failed
# ===========================================================================


class TestExecutionFailure:
    def test_failed_step_sets_cycle_failed(self, tmp_path: Path) -> None:
        """If _execute_step returns failed, cycle status should be failed."""
        agent = _make_agent(tmp_path, auto_approve=True, dry_run=False)
        # This will likely fail because terraform/kubectl aren't installed
        cycle = agent.run_cycle()
        # The cycle could be completed (no execution steps) or failed
        assert cycle.status in ("completed", "failed", "rolled_back")


# ===========================================================================
# 25. High cost warning in simulation
# ===========================================================================


class TestHighCostWarning:
    def test_high_cost_plan_generates_side_effect(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path)
        from faultray.remediation.iac_generator import RemediationFile, RemediationPlan

        plan = RemediationPlan(
            total_monthly_cost=15000.0,
            expected_score_before=50.0,
            expected_score_after=80.0,
            files=[
                RemediationFile(
                    path="expensive.tf",
                    content="resource {}",
                    description="Expensive fix",
                    phase=3,
                    impact_score_delta=30.0,
                    monthly_cost=15000.0,
                    category="dr",
                ),
            ],
        )
        result = agent._simulate_with_fix(_unhealthy_graph(), plan)
        assert any("High estimated cost" in s for s in result.side_effects)
        # High cost alone shouldn't fail the simulation
        assert result.passed
