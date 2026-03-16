"""Tests for the Incident Response Simulator."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    OperationalProfile,
    OperationalTeamConfig,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.incident_response_simulator import (
    AutomationOpportunity,
    AutomationReport,
    CommunicationEffectiveness,
    CommunicationPlan,
    EscalationAction,
    EscalationChain,
    EscalationStep,
    IncidentCategory,
    IncidentPattern,
    IncidentResponseResult,
    IncidentResponseSimulator,
    IncidentTimelineReconstruction,
    MTTREstimate,
    OnCallFatigueMetrics,
    OnCallFatigueReport,
    PIRTemplate,
    RecoveryAction,
    RecoveryActionType,
    RecoveryPlan,
    RunbookCoverage,
    RunbookCoverageReport,
    SeverityLevel,
    TimelineEntry,
    _BASE_MTTR_BY_TYPE,
    _COMPONENT_TYPE_CATEGORY,
    _FAILURE_MODES_BY_TYPE,
    _RECOVERY_ACTIONS_BY_TYPE,
    _SEVERITY_ESCALATION_MINUTES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(cid="c1", ctype=ComponentType.APP_SERVER, **kwargs):
    defaults = dict(id=cid, name=cid, type=ctype)
    defaults.update(kwargs)
    return Component(**defaults)


def _graph(*comps):
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _simple_graph():
    """A 3-node graph: lb -> app -> db."""
    lb = _comp("lb", ComponentType.LOAD_BALANCER, replicas=2)
    app = _comp("app", ComponentType.APP_SERVER, replicas=2)
    db = _comp("db", ComponentType.DATABASE, replicas=1)
    g = _graph(lb, app, db)
    g.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return g


def _resilient_graph():
    """Graph with failover, autoscaling, and high team readiness."""
    lb = _comp(
        "lb", ComponentType.LOAD_BALANCER,
        replicas=3,
        failover=FailoverConfig(enabled=True, promotion_time_seconds=5.0),
    )
    app = _comp(
        "app", ComponentType.APP_SERVER,
        replicas=3,
        failover=FailoverConfig(enabled=True, promotion_time_seconds=10.0),
        autoscaling=AutoScalingConfig(enabled=True),
        team=OperationalTeamConfig(
            team_size=5,
            runbook_coverage_percent=90.0,
            automation_percent=70.0,
            mean_acknowledge_time_minutes=2.0,
        ),
    )
    db = _comp(
        "db", ComponentType.DATABASE,
        replicas=2,
        failover=FailoverConfig(enabled=True, promotion_time_seconds=30.0),
        team=OperationalTeamConfig(
            team_size=4,
            runbook_coverage_percent=80.0,
            automation_percent=50.0,
        ),
    )
    g = _graph(lb, app, db)
    g.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return g


def _wide_graph():
    """Graph with many components depending on one: hub topology."""
    hub = _comp("hub", ComponentType.DATABASE, replicas=1)
    comps = [hub]
    deps = []
    for i in range(6):
        c = _comp(f"svc{i}", ComponentType.APP_SERVER, replicas=1)
        comps.append(c)
        deps.append(Dependency(source_id=f"svc{i}", target_id="hub", dependency_type="requires"))
    g = _graph(*comps)
    for d in deps:
        g.add_dependency(d)
    return g


# ---------------------------------------------------------------------------
# Test: Severity classification
# ---------------------------------------------------------------------------


class TestSeverityClassification:
    def test_classify_severity_default(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        sev = sim.classify_severity("app", SeverityLevel.SEV3)
        # app has replicas=2, so no escalation from replicas
        assert sev in list(SeverityLevel)

    def test_classify_severity_escalates_for_large_blast_radius(self):
        g = _wide_graph()
        sim = IncidentResponseSimulator(g)
        # hub affects >50% of components
        sev = sim.classify_severity("hub", SeverityLevel.SEV3)
        assert sev == SeverityLevel.SEV2 or sev == SeverityLevel.SEV1

    def test_classify_severity_escalates_for_spof_with_dependents(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        # db has 1 replica and app requires it
        sev = sim.classify_severity("db", SeverityLevel.SEV4)
        # Should escalate at least one level
        assert sev.value <= "SEV3"

    def test_classify_severity_nonexistent_component(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        sev = sim.classify_severity("nonexistent", SeverityLevel.SEV3)
        assert sev == SeverityLevel.SEV3

    def test_classify_severity_already_sev1_no_further_escalation(self):
        g = _wide_graph()
        sim = IncidentResponseSimulator(g)
        sev = sim.classify_severity("hub", SeverityLevel.SEV1)
        assert sev == SeverityLevel.SEV1


# ---------------------------------------------------------------------------
# Test: MTTR estimation
# ---------------------------------------------------------------------------


class TestMTTREstimation:
    def test_estimate_mttr_basic(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        mttr = sim.estimate_mttr("app")
        assert mttr.component_id == "app"
        assert mttr.base_mttr_minutes > 0
        assert mttr.adjusted_mttr_minutes > 0

    def test_estimate_mttr_larger_team_reduces_time(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        mttr_small = sim.estimate_mttr("app", team_size=1)
        mttr_large = sim.estimate_mttr("app", team_size=10)
        assert mttr_large.adjusted_mttr_minutes < mttr_small.adjusted_mttr_minutes

    def test_estimate_mttr_automation_reduces_time(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        mttr_manual = sim.estimate_mttr("app", automation_level=0.0)
        mttr_auto = sim.estimate_mttr("app", automation_level=1.0)
        assert mttr_auto.adjusted_mttr_minutes < mttr_manual.adjusted_mttr_minutes

    def test_estimate_mttr_runbook_reduces_time(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        mttr_no_rb = sim.estimate_mttr("app", has_runbook=False)
        mttr_rb = sim.estimate_mttr("app", has_runbook=True)
        assert mttr_rb.adjusted_mttr_minutes < mttr_no_rb.adjusted_mttr_minutes

    def test_estimate_mttr_failover_reduces_time(self):
        g = _resilient_graph()
        sim = IncidentResponseSimulator(g)
        mttr_resilient = sim.estimate_mttr("app")

        g2 = _simple_graph()
        sim2 = IncidentResponseSimulator(g2)
        mttr_basic = sim2.estimate_mttr("app")

        assert mttr_resilient.adjusted_mttr_minutes < mttr_basic.adjusted_mttr_minutes

    def test_estimate_mttr_uses_operational_profile(self):
        comp = _comp(
            "db", ComponentType.DATABASE,
            operational_profile=OperationalProfile(mttr_minutes=10.0),
        )
        g = _graph(comp)
        sim = IncidentResponseSimulator(g)
        mttr = sim.estimate_mttr("db")
        assert mttr.base_mttr_minutes == 10.0

    def test_estimate_mttr_nonexistent_raises(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        with pytest.raises(ValueError, match="not found"):
            sim.estimate_mttr("ghost")

    def test_estimate_mttr_breakdown_keys(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        mttr = sim.estimate_mttr("app")
        expected_keys = {
            "base", "team_factor", "automation_factor",
            "runbook_factor", "complexity_factor", "infra_factor", "adjusted",
        }
        assert set(mttr.breakdown.keys()) == expected_keys

    def test_estimate_mttr_minimum_one_minute(self):
        """MTTR should never be less than 1 minute."""
        comp = _comp(
            "cache", ComponentType.CACHE,
            replicas=5,
            failover=FailoverConfig(enabled=True),
            operational_profile=OperationalProfile(mttr_minutes=1.0),
        )
        g = _graph(comp)
        sim = IncidentResponseSimulator(g)
        mttr = sim.estimate_mttr(
            "cache", team_size=20, automation_level=1.0, has_runbook=True
        )
        assert mttr.adjusted_mttr_minutes >= 1.0


# ---------------------------------------------------------------------------
# Test: Escalation chain
# ---------------------------------------------------------------------------


class TestEscalationChain:
    def test_sev1_escalation_has_all_levels(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        chain = sim.build_escalation_chain(SeverityLevel.SEV1)
        assert len(chain.steps) >= 5
        assert chain.auto_escalate is True
        actions = {s.action for s in chain.steps}
        assert EscalationAction.ASSEMBLE_WAR_ROOM in actions
        assert EscalationAction.EXECUTIVE_BRIEFING in actions

    def test_sev3_escalation_limited(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        chain = sim.build_escalation_chain(SeverityLevel.SEV3)
        assert len(chain.steps) == 2
        assert chain.auto_escalate is False

    def test_sev5_escalation_minimal(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        chain = sim.build_escalation_chain(SeverityLevel.SEV5)
        assert len(chain.steps) == 1
        assert chain.steps[0].action == EscalationAction.PAGE_ONCALL

    def test_escalation_time_is_positive(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        for sev in SeverityLevel:
            chain = sim.build_escalation_chain(sev)
            assert chain.total_escalation_time_minutes >= 0

    def test_sev2_has_stakeholder_notification(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        chain = sim.build_escalation_chain(SeverityLevel.SEV2)
        actions = {s.action for s in chain.steps}
        assert EscalationAction.NOTIFY_STAKEHOLDERS in actions


# ---------------------------------------------------------------------------
# Test: Communication effectiveness
# ---------------------------------------------------------------------------


class TestCommunicationEffectiveness:
    def test_sev1_has_many_notification_plans(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        eff = sim.assess_communication_effectiveness(SeverityLevel.SEV1)
        assert len(eff.plans) >= 4
        assert eff.coverage_score > 0

    def test_sev5_has_minimal_plans(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        eff = sim.assess_communication_effectiveness(SeverityLevel.SEV5)
        assert len(eff.plans) == 2  # engineering + oncall

    def test_small_team_creates_gap(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        eff = sim.assess_communication_effectiveness(SeverityLevel.SEV1, team_size=1)
        assert len(eff.gaps) >= 1
        assert any("Single-person" in gap for gap in eff.gaps)

    def test_notification_delays_are_nonnegative(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        eff = sim.assess_communication_effectiveness(SeverityLevel.SEV2)
        assert eff.average_notification_delay_minutes >= 0
        assert eff.max_notification_delay_minutes >= eff.average_notification_delay_minutes


# ---------------------------------------------------------------------------
# Test: Runbook coverage assessment
# ---------------------------------------------------------------------------


class TestRunbookCoverage:
    def test_runbook_coverage_report_structure(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        report = sim.assess_runbook_coverage()
        assert isinstance(report, RunbookCoverageReport)
        assert len(report.per_component) == 3
        assert report.total_failure_modes > 0

    def test_high_coverage_components(self):
        comp = _comp(
            "app", ComponentType.APP_SERVER,
            team=OperationalTeamConfig(runbook_coverage_percent=100.0),
        )
        g = _graph(comp)
        sim = IncidentResponseSimulator(g)
        report = sim.assess_runbook_coverage()
        assert report.per_component[0].coverage_percent == 100.0

    def test_low_coverage_generates_recommendations(self):
        comp = _comp(
            "db", ComponentType.DATABASE,
            team=OperationalTeamConfig(runbook_coverage_percent=10.0),
        )
        g = _graph(comp)
        sim = IncidentResponseSimulator(g)
        report = sim.assess_runbook_coverage()
        assert len(report.recommendations) >= 1
        assert report.overall_coverage_percent < 50.0

    def test_empty_graph_coverage(self):
        g = _graph()
        sim = IncidentResponseSimulator(g)
        report = sim.assess_runbook_coverage()
        assert report.total_failure_modes == 0
        assert report.overall_coverage_percent == 0.0


# ---------------------------------------------------------------------------
# Test: On-call fatigue analysis
# ---------------------------------------------------------------------------


class TestOnCallFatigue:
    def test_fatigue_report_structure(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        report = sim.analyze_oncall_fatigue()
        assert isinstance(report, OnCallFatigueReport)
        assert len(report.per_component) == 3

    def test_high_mtbf_low_fatigue(self):
        comp = _comp(
            "app", ComponentType.APP_SERVER,
            operational_profile=OperationalProfile(mtbf_hours=8760.0),  # once/year
        )
        g = _graph(comp)
        sim = IncidentResponseSimulator(g)
        report = sim.analyze_oncall_fatigue()
        assert report.per_component[0].fatigue_score < 25.0
        assert report.per_component[0].risk_level == "low"

    def test_low_mtbf_high_fatigue(self):
        comp = _comp(
            "db", ComponentType.DATABASE,
            operational_profile=OperationalProfile(mtbf_hours=5.0),
        )
        g = _graph(comp)
        sim = IncidentResponseSimulator(g)
        report = sim.analyze_oncall_fatigue()
        metric = report.per_component[0]
        assert metric.fatigue_score > 50.0
        assert metric.risk_level in ("high", "critical")

    def test_rotation_gap_detected(self):
        comp = _comp(
            "app", ComponentType.APP_SERVER,
            team=OperationalTeamConfig(oncall_coverage_hours=16.0),
        )
        g = _graph(comp)
        sim = IncidentResponseSimulator(g)
        report = sim.analyze_oncall_fatigue()
        metric = report.per_component[0]
        assert metric.rotation_gap_hours == 8.0
        assert any("rotation gap" in r for r in report.recommendations)

    def test_empty_graph_fatigue(self):
        g = _graph()
        sim = IncidentResponseSimulator(g)
        report = sim.analyze_oncall_fatigue()
        assert report.average_fatigue_score == 0.0


# ---------------------------------------------------------------------------
# Test: Incident categorization and pattern detection
# ---------------------------------------------------------------------------


class TestIncidentCategorization:
    def test_categorize_database(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        cat = sim.categorize_incident("db")
        assert cat == IncidentCategory.DATABASE

    def test_categorize_app_server(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        cat = sim.categorize_incident("app")
        assert cat == IncidentCategory.APPLICATION

    def test_categorize_lb_is_network(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        cat = sim.categorize_incident("lb")
        assert cat == IncidentCategory.NETWORK

    def test_categorize_nonexistent_is_unknown(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        cat = sim.categorize_incident("ghost")
        assert cat == IncidentCategory.UNKNOWN

    def test_detect_patterns_returns_patterns(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        patterns = sim.detect_patterns()
        assert len(patterns) >= 1
        categories = {p.category for p in patterns}
        assert IncidentCategory.DATABASE in categories or IncidentCategory.APPLICATION in categories

    def test_detect_patterns_frequency_from_mtbf(self):
        comp = _comp(
            "db", ComponentType.DATABASE,
            operational_profile=OperationalProfile(mtbf_hours=100.0),
        )
        g = _graph(comp)
        sim = IncidentResponseSimulator(g)
        patterns = sim.detect_patterns()
        assert len(patterns) == 1
        # 730h / 100h * 1 component = ~7.3 per month
        assert patterns[0].estimated_frequency_per_month > 5.0


# ---------------------------------------------------------------------------
# Test: Recovery plan and dependency ordering
# ---------------------------------------------------------------------------


class TestRecoveryPlan:
    def test_build_recovery_plan_single_component(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        plan = sim.build_recovery_plan("db")
        assert isinstance(plan, RecoveryPlan)
        assert plan.total_actions > 0
        assert plan.critical_path_minutes > 0

    def test_build_recovery_plan_multiple_affected(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        plan = sim.build_recovery_plan("db", affected_ids=["db", "app"])
        assert plan.total_actions >= 4  # at least some actions for each

    def test_recovery_plan_parallel_groups_exist(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        plan = sim.build_recovery_plan("db", affected_ids=["db", "app"])
        assert len(plan.parallel_groups) >= 1

    def test_recovery_plan_actions_have_correct_types(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        plan = sim.build_recovery_plan("app")
        for action in plan.actions:
            assert isinstance(action.action_type, RecoveryActionType)
            assert action.estimated_minutes > 0

    def test_recovery_plan_dependency_ordering(self):
        """Dependencies should be recovered before dependents."""
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        plan = sim.build_recovery_plan("app", affected_ids=["app", "db"])
        # db actions should come before app actions in the plan
        db_indices = [i for i, a in enumerate(plan.actions) if a.component_id == "db"]
        app_indices = [i for i, a in enumerate(plan.actions) if a.component_id == "app"]
        if db_indices and app_indices:
            assert min(db_indices) < min(app_indices)


# ---------------------------------------------------------------------------
# Test: Automation opportunity scoring
# ---------------------------------------------------------------------------


class TestAutomationScoring:
    def test_automation_report_structure(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        plan = sim.build_recovery_plan("app")
        report = sim.score_automation_opportunities(plan)
        assert isinstance(report, AutomationReport)
        assert len(report.opportunities) > 0
        assert report.total_manual_time_minutes > 0

    def test_automation_sorted_by_priority(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        plan = sim.build_recovery_plan("app")
        report = sim.score_automation_opportunities(plan)
        priorities = [o.priority_score for o in report.opportunities]
        assert priorities == sorted(priorities, reverse=True)

    def test_automation_savings_nonnegative(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        plan = sim.build_recovery_plan("db")
        report = sim.score_automation_opportunities(plan)
        for opp in report.opportunities:
            assert opp.time_savings_minutes >= 0
            assert opp.estimated_automated_time_minutes <= opp.current_manual_time_minutes

    def test_automation_coverage_percentage(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        plan = sim.build_recovery_plan("app")
        report = sim.score_automation_opportunities(plan)
        assert 0 <= report.automation_coverage_percent <= 100

    def test_empty_plan_automation(self):
        plan = RecoveryPlan()
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        report = sim.score_automation_opportunities(plan)
        assert report.total_manual_time_minutes == 0.0
        assert report.automation_coverage_percent == 0.0


# ---------------------------------------------------------------------------
# Test: Timeline reconstruction
# ---------------------------------------------------------------------------


class TestTimelineReconstruction:
    def test_timeline_has_ordered_entries(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        tl = sim.reconstruct_timeline("app", SeverityLevel.SEV3)
        assert len(tl.entries) >= 5
        offsets = [e.timestamp_offset_minutes for e in tl.entries]
        assert offsets == sorted(offsets)

    def test_timeline_sev1_includes_escalation(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        tl = sim.reconstruct_timeline("app", SeverityLevel.SEV1)
        phases = {e.phase for e in tl.entries}
        assert "Escalation" in phases

    def test_timeline_with_runbook_has_runbook_entry(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        tl = sim.reconstruct_timeline("app", SeverityLevel.SEV3, has_runbook=True)
        has_runbook_entry = any("unbook" in e.description for e in tl.entries)
        assert has_runbook_entry

    def test_timeline_durations_positive(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        tl = sim.reconstruct_timeline("db", SeverityLevel.SEV2)
        assert tl.total_duration_minutes > 0
        assert tl.time_to_detect_minutes > 0
        assert tl.time_to_acknowledge_minutes > tl.time_to_detect_minutes
        assert tl.time_to_mitigate_minutes > tl.time_to_acknowledge_minutes
        assert tl.time_to_resolve_minutes > tl.time_to_mitigate_minutes


# ---------------------------------------------------------------------------
# Test: PIR template generation
# ---------------------------------------------------------------------------


class TestPIRTemplate:
    def test_pir_template_structure(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        mttr = sim.estimate_mttr("app")
        tl = sim.reconstruct_timeline("app", SeverityLevel.SEV2)
        pir = sim.generate_pir_template(
            "app", SeverityLevel.SEV2, ["app", "lb"], mttr, tl,
        )
        assert isinstance(pir, PIRTemplate)
        assert pir.severity == SeverityLevel.SEV2
        assert len(pir.timeline_entries) > 0
        assert len(pir.five_whys) == 5
        assert pir.incident_id.startswith("INC-")

    def test_pir_has_action_items_for_spof(self):
        db = _comp("db", ComponentType.DATABASE, replicas=1)
        g = _graph(db)
        sim = IncidentResponseSimulator(g)
        mttr = sim.estimate_mttr("db")
        tl = sim.reconstruct_timeline("db", SeverityLevel.SEV2)
        pir = sim.generate_pir_template(
            "db", SeverityLevel.SEV2, ["db"], mttr, tl,
        )
        actions = [a["action"] for a in pir.action_items]
        assert any("replica" in a.lower() for a in actions)

    def test_pir_lessons_for_large_blast_radius(self):
        g = _wide_graph()
        sim = IncidentResponseSimulator(g)
        affected = sim._get_affected_components("hub")
        mttr = sim.estimate_mttr("hub")
        tl = sim.reconstruct_timeline("hub", SeverityLevel.SEV1)
        pir = sim.generate_pir_template(
            "hub", SeverityLevel.SEV1, affected, mttr, tl,
        )
        assert any("blast radius" in lesson.lower() for lesson in pir.lessons_learned)

    def test_pir_contributing_factors_for_poor_config(self):
        db = _comp(
            "db", ComponentType.DATABASE,
            replicas=1,
            team=OperationalTeamConfig(
                runbook_coverage_percent=10.0,
                automation_percent=5.0,
            ),
        )
        g = _graph(db)
        sim = IncidentResponseSimulator(g)
        mttr = sim.estimate_mttr("db")
        tl = sim.reconstruct_timeline("db", SeverityLevel.SEV3)
        pir = sim.generate_pir_template("db", SeverityLevel.SEV3, ["db"], mttr, tl)
        factors = pir.contributing_factors
        assert any("single point" in f.lower() for f in factors)
        assert any("runbook" in f.lower() for f in factors)


# ---------------------------------------------------------------------------
# Test: Full simulation
# ---------------------------------------------------------------------------


class TestFullSimulation:
    def test_simulate_incident_basic(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        result = sim.simulate_incident("app", severity=SeverityLevel.SEV3)
        assert isinstance(result, IncidentResponseResult)
        assert result.severity in list(SeverityLevel)
        assert result.affected_component_id == "app"
        assert result.mttr_estimate is not None
        assert result.escalation_chain is not None
        assert result.recovery_plan is not None
        assert result.timeline is not None
        assert result.pir_template is not None
        assert result.automation_report is not None
        assert 0 <= result.overall_readiness_score <= 100

    def test_simulate_incident_nonexistent_raises(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        with pytest.raises(ValueError, match="not found"):
            sim.simulate_incident("ghost")

    def test_simulate_incident_resilient_has_higher_readiness(self):
        g_basic = _simple_graph()
        g_resilient = _resilient_graph()
        sim_basic = IncidentResponseSimulator(g_basic)
        sim_resilient = IncidentResponseSimulator(g_resilient)

        result_basic = sim_basic.simulate_incident(
            "app", severity=SeverityLevel.SEV2, has_runbook=False,
        )
        result_resilient = sim_resilient.simulate_incident(
            "app", severity=SeverityLevel.SEV2,
            has_runbook=True, automation_level=0.8,
        )

        assert result_resilient.overall_readiness_score > result_basic.overall_readiness_score

    def test_simulate_incident_affected_components(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        result = sim.simulate_incident("db")
        # app depends on db, lb depends on app -> both affected
        assert len(result.affected_component_ids) >= 1
        assert "db" in result.affected_component_ids

    def test_simulate_incident_sev1_full_escalation(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        result = sim.simulate_incident("db", severity=SeverityLevel.SEV1)
        assert result.severity in (SeverityLevel.SEV1, SeverityLevel.SEV2)
        assert result.escalation_chain is not None
        assert len(result.escalation_chain.steps) >= 5

    def test_simulate_incident_automation_clamp(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        # Automation level > 1.0 should be clamped
        result = sim.simulate_incident("app", automation_level=2.0)
        assert result.mttr_estimate is not None
        # Automation level < 0.0 should be clamped
        result2 = sim.simulate_incident("app", automation_level=-1.0)
        assert result2.mttr_estimate is not None

    def test_simulate_incident_category_detection(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        result = sim.simulate_incident("db")
        assert result.category == IncidentCategory.DATABASE


# ---------------------------------------------------------------------------
# Test: Lookup table coverage
# ---------------------------------------------------------------------------


class TestLookupTables:
    def test_all_component_types_have_base_mttr(self):
        for ct in ComponentType:
            assert ct.value in _BASE_MTTR_BY_TYPE

    def test_all_component_types_have_category(self):
        for ct in ComponentType:
            assert ct.value in _COMPONENT_TYPE_CATEGORY

    def test_all_component_types_have_failure_modes(self):
        for ct in ComponentType:
            assert ct.value in _FAILURE_MODES_BY_TYPE
            assert len(_FAILURE_MODES_BY_TYPE[ct.value]) >= 1

    def test_all_component_types_have_recovery_actions(self):
        for ct in ComponentType:
            assert ct.value in _RECOVERY_ACTIONS_BY_TYPE
            assert len(_RECOVERY_ACTIONS_BY_TYPE[ct.value]) >= 1

    def test_all_severity_levels_have_escalation_minutes(self):
        for sev in SeverityLevel:
            assert sev in _SEVERITY_ESCALATION_MINUTES
            assert _SEVERITY_ESCALATION_MINUTES[sev] > 0

    def test_severity_escalation_minutes_ordering(self):
        """SEV1 should have shortest escalation window."""
        assert _SEVERITY_ESCALATION_MINUTES[SeverityLevel.SEV1] < _SEVERITY_ESCALATION_MINUTES[SeverityLevel.SEV5]


# ---------------------------------------------------------------------------
# Test: Edge cases and dataclass construction
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_single_component_graph(self):
        comp = _comp("solo", ComponentType.APP_SERVER)
        g = _graph(comp)
        sim = IncidentResponseSimulator(g)
        result = sim.simulate_incident("solo")
        assert result.affected_component_id == "solo"
        assert result.overall_readiness_score >= 0

    def test_dataclass_defaults(self):
        step = EscalationStep(
            level=1,
            action=EscalationAction.PAGE_ONCALL,
            target_role="On-Call",
            trigger_condition="Alert",
            time_threshold_minutes=5.0,
            expected_response_minutes=3.0,
        )
        assert step.level == 1

        entry = TimelineEntry(
            timestamp_offset_minutes=0.0,
            phase="Detection",
            description="Alert",
            actor="System",
            action_type="alert",
        )
        assert entry.phase == "Detection"

        action = RecoveryAction(
            action_id="a1",
            action_type=RecoveryActionType.RESTART_SERVICE,
            component_id="c1",
            description="Restart",
            estimated_minutes=5.0,
        )
        assert action.depends_on == []
        assert action.can_automate is False

    def test_external_api_component(self):
        comp = _comp("ext", ComponentType.EXTERNAL_API)
        g = _graph(comp)
        sim = IncidentResponseSimulator(g)
        result = sim.simulate_incident("ext")
        assert result.category == IncidentCategory.THIRD_PARTY

    def test_custom_component_type(self):
        comp = _comp("custom", ComponentType.CUSTOM)
        g = _graph(comp)
        sim = IncidentResponseSimulator(g)
        cat = sim.categorize_incident("custom")
        assert cat == IncidentCategory.UNKNOWN

    def test_detect_patterns_empty_graph(self):
        g = _graph()
        sim = IncidentResponseSimulator(g)
        patterns = sim.detect_patterns()
        assert patterns == []

    def test_recovery_plan_empty_affected(self):
        g = _simple_graph()
        sim = IncidentResponseSimulator(g)
        plan = sim.build_recovery_plan("app", affected_ids=[])
        assert plan.total_actions > 0  # at least the primary component

    def test_pir_template_detection_effectiveness(self):
        comp = _comp(
            "fast", ComponentType.CACHE,
            team=OperationalTeamConfig(mean_acknowledge_time_minutes=1.0),
        )
        g = _graph(comp)
        sim = IncidentResponseSimulator(g)
        mttr = sim.estimate_mttr("fast", team_size=5, automation_level=0.9, has_runbook=True)
        tl = sim.reconstruct_timeline("fast", SeverityLevel.SEV5, team_size=5)
        pir = sim.generate_pir_template("fast", SeverityLevel.SEV5, ["fast"], mttr, tl)
        assert pir.detection_effectiveness in ("Good", "Needs improvement")

    def test_wide_graph_blast_radius_in_pir(self):
        g = _wide_graph()
        sim = IncidentResponseSimulator(g)
        result = sim.simulate_incident("hub", severity=SeverityLevel.SEV1)
        assert result.pir_template is not None
        assert len(result.pir_template.action_items) >= 1
