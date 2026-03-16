"""Tests for the Runbook Validation Engine (v2).

Comprehensive test suite covering RunbookStepType/ValidationResult enums,
RunbookStep/RunbookV2/StepValidation/CoverageGap/EscalationValidation/
RunbookDiff/RunbookComparison/RunbookValidationReport models,
RunbookValidationEngine methods (validate_runbook, find_coverage_gaps,
estimate_mttr, detect_stale_runbooks, suggest_runbook,
validate_escalation_path, compare_runbooks), edge cases, and integration.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.runbook_validator import (
    # v2 Pydantic-based classes
    CoverageGap,
    EscalationValidation,
    RunbookComparison,
    RunbookDiff,
    RunbookStep,
    RunbookStepType,
    RunbookV2,
    RunbookValidationEngine,
    RunbookValidationReportV2,
    StepValidation,
    ValidationResult,
    # v1 dataclass-based classes (legacy)
    Runbook as RunbookV1,
    RunbookGap,
    RunbookStatus,
    RunbookValidationReport as RunbookValidationReportV1,
    RunbookValidator,
    RecoveryStep,
)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str | None = None,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 2,
    failover_enabled: bool = False,
) -> Component:
    return Component(
        id=cid,
        name=name or cid,
        type=ctype,
        replicas=replicas,
        failover=FailoverConfig(enabled=failover_enabled),
    )


def _graph(*components: Component, deps: list[Dependency] | None = None) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for d in deps or []:
        g.add_dependency(d)
    return g


def _step(
    num: int = 1,
    desc: str = "Do something",
    stype: RunbookStepType = RunbookStepType.REMEDIATION,
    target: str = "app",
    outcome: str = "Fixed",
    timeout: float = 300.0,
    approval: bool = False,
) -> RunbookStep:
    return RunbookStep(
        step_number=num,
        description=desc,
        step_type=stype,
        target_component_id=target,
        expected_outcome=outcome,
        timeout_seconds=timeout,
        requires_approval=approval,
    )


def _runbook(
    rid: str = "rb-1",
    name: str = "Test Runbook",
    scenario: str = "oom_kill",
    steps: list[RunbookStep] | None = None,
    last_tested: str = "2026-01-01",
    owner: str = "team-a",
    severity: str = "high",
) -> RunbookV2:
    return RunbookV2(
        id=rid,
        name=name,
        scenario=scenario,
        steps=steps or [],
        last_tested=last_tested,
        owner=owner,
        severity=severity,
    )


# ---------------------------------------------------------------------------
# RunbookStepType enum tests
# ---------------------------------------------------------------------------


class TestRunbookStepType:
    def test_diagnostic_value(self):
        assert RunbookStepType.DIAGNOSTIC == "diagnostic"

    def test_remediation_value(self):
        assert RunbookStepType.REMEDIATION == "remediation"

    def test_escalation_value(self):
        assert RunbookStepType.ESCALATION == "escalation"

    def test_verification_value(self):
        assert RunbookStepType.VERIFICATION == "verification"

    def test_rollback_value(self):
        assert RunbookStepType.ROLLBACK == "rollback"

    def test_notification_value(self):
        assert RunbookStepType.NOTIFICATION == "notification"

    def test_manual_check_value(self):
        assert RunbookStepType.MANUAL_CHECK == "manual_check"

    def test_member_count(self):
        assert len(RunbookStepType) == 7


# ---------------------------------------------------------------------------
# ValidationResult enum tests
# ---------------------------------------------------------------------------


class TestValidationResult:
    def test_valid_value(self):
        assert ValidationResult.VALID == "valid"

    def test_stale_value(self):
        assert ValidationResult.STALE == "stale"

    def test_incomplete_value(self):
        assert ValidationResult.INCOMPLETE == "incomplete"

    def test_incorrect_value(self):
        assert ValidationResult.INCORRECT == "incorrect"

    def test_untestable_value(self):
        assert ValidationResult.UNTESTABLE == "untestable"

    def test_missing_component_value(self):
        assert ValidationResult.MISSING_COMPONENT == "missing_component"

    def test_member_count(self):
        assert len(ValidationResult) == 6


# ---------------------------------------------------------------------------
# RunbookStep model tests
# ---------------------------------------------------------------------------


class TestRunbookStep:
    def test_create_basic(self):
        s = _step()
        assert s.step_number == 1
        assert s.step_type == RunbookStepType.REMEDIATION

    def test_requires_approval_default(self):
        s = _step(approval=False)
        assert s.requires_approval is False

    def test_requires_approval_true(self):
        s = _step(approval=True)
        assert s.requires_approval is True

    def test_timeout_seconds(self):
        s = _step(timeout=120.5)
        assert s.timeout_seconds == 120.5

    def test_description(self):
        s = _step(desc="Restart app server")
        assert s.description == "Restart app server"

    def test_target_component_id(self):
        s = _step(target="db-primary")
        assert s.target_component_id == "db-primary"

    def test_expected_outcome(self):
        s = _step(outcome="Server healthy")
        assert s.expected_outcome == "Server healthy"


# ---------------------------------------------------------------------------
# RunbookV2 model tests
# ---------------------------------------------------------------------------


class TestRunbookV2:
    def test_create_empty_steps(self):
        rb = _runbook(steps=[])
        assert rb.steps == []

    def test_create_with_steps(self):
        rb = _runbook(steps=[_step(1), _step(2)])
        assert len(rb.steps) == 2

    def test_id_field(self):
        rb = _runbook(rid="my-rb")
        assert rb.id == "my-rb"

    def test_scenario_field(self):
        rb = _runbook(scenario="disk_full")
        assert rb.scenario == "disk_full"

    def test_owner_field(self):
        rb = _runbook(owner="sre-team")
        assert rb.owner == "sre-team"

    def test_severity_field(self):
        rb = _runbook(severity="critical")
        assert rb.severity == "critical"

    def test_last_tested_field(self):
        rb = _runbook(last_tested="2025-12-01")
        assert rb.last_tested == "2025-12-01"


# ---------------------------------------------------------------------------
# StepValidation model tests
# ---------------------------------------------------------------------------


class TestStepValidation:
    def test_create(self):
        sv = StepValidation(
            step_number=1,
            result=ValidationResult.VALID,
            reason="OK",
            suggestion="",
        )
        assert sv.result == ValidationResult.VALID

    def test_missing_component(self):
        sv = StepValidation(
            step_number=2,
            result=ValidationResult.MISSING_COMPONENT,
            reason="Not found",
            suggestion="Fix it",
        )
        assert sv.result == ValidationResult.MISSING_COMPONENT


# ---------------------------------------------------------------------------
# CoverageGap model tests
# ---------------------------------------------------------------------------


class TestCoverageGap:
    def test_create(self):
        cg = CoverageGap(
            component_id="db",
            component_name="Database",
            failure_scenario="replication_lag",
            severity="high",
        )
        assert cg.component_id == "db"
        assert cg.failure_scenario == "replication_lag"


# ---------------------------------------------------------------------------
# EscalationValidation model tests
# ---------------------------------------------------------------------------


class TestEscalationValidation:
    def test_valid(self):
        ev = EscalationValidation(
            has_escalation=True,
            escalation_steps=[3],
            has_notification=True,
            notification_steps=[2],
            issues=[],
            is_valid=True,
        )
        assert ev.is_valid is True

    def test_invalid(self):
        ev = EscalationValidation(
            has_escalation=False,
            escalation_steps=[],
            has_notification=False,
            notification_steps=[],
            issues=["Missing escalation"],
            is_valid=False,
        )
        assert ev.is_valid is False


# ---------------------------------------------------------------------------
# RunbookDiff / RunbookComparison model tests
# ---------------------------------------------------------------------------


class TestRunbookDiff:
    def test_create(self):
        d = RunbookDiff(field="name", old_value="A", new_value="B")
        assert d.field == "name"


class TestRunbookComparison:
    def test_identical(self):
        c = RunbookComparison(
            runbook_a_id="a",
            runbook_b_id="b",
            is_identical=True,
        )
        assert c.is_identical is True
        assert c.differences == []

    def test_with_changes(self):
        c = RunbookComparison(
            runbook_a_id="a",
            runbook_b_id="b",
            steps_added=[3],
            steps_removed=[1],
            steps_modified=[2],
            is_identical=False,
        )
        assert c.is_identical is False
        assert c.steps_added == [3]


# ---------------------------------------------------------------------------
# RunbookValidationReport model tests
# ---------------------------------------------------------------------------


class TestRunbookValidationReportModel:
    def test_create(self):
        r = RunbookValidationReportV2(
            runbook_id="rb-1",
            overall_result=ValidationResult.VALID,
            step_validations=[],
            coverage_gaps=[],
            staleness_days=10,
            recommendations=[],
            estimated_mttr_minutes=5.0,
            confidence=1.0,
        )
        assert r.overall_result == ValidationResult.VALID

    def test_confidence_range(self):
        r = RunbookValidationReportV2(
            runbook_id="rb-1",
            overall_result=ValidationResult.VALID,
            step_validations=[],
            coverage_gaps=[],
            staleness_days=0,
            recommendations=[],
            estimated_mttr_minutes=0.0,
            confidence=0.5,
        )
        assert 0.0 <= r.confidence <= 1.0


# ---------------------------------------------------------------------------
# RunbookValidationEngine.validate_runbook tests
# ---------------------------------------------------------------------------


class TestValidateRunbook:
    def test_valid_runbook(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            steps=[
                _step(1, stype=RunbookStepType.DIAGNOSTIC),
                _step(2, stype=RunbookStepType.REMEDIATION),
                _step(3, stype=RunbookStepType.VERIFICATION),
            ],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert report.overall_result == ValidationResult.VALID

    def test_missing_component_step(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            steps=[_step(1, target="nonexistent")],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert report.overall_result == ValidationResult.MISSING_COMPONENT

    def test_negative_timeout_step(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            steps=[_step(1, timeout=-1)],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert report.step_validations[0].result == ValidationResult.INCORRECT

    def test_zero_timeout_step(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            steps=[_step(1, timeout=0)],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert report.step_validations[0].result == ValidationResult.INCORRECT

    def test_very_large_timeout(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            steps=[_step(1, timeout=7200)],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert report.step_validations[0].result == ValidationResult.UNTESTABLE

    def test_empty_description(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            steps=[_step(1, desc="  ")],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert report.step_validations[0].result == ValidationResult.INCOMPLETE

    def test_empty_expected_outcome(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            steps=[_step(1, outcome="")],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert report.step_validations[0].result == ValidationResult.INCOMPLETE

    def test_stale_runbook_over_90_days(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested="2025-01-01",
            steps=[
                _step(1, stype=RunbookStepType.DIAGNOSTIC),
                _step(2, stype=RunbookStepType.REMEDIATION),
                _step(3, stype=RunbookStepType.VERIFICATION),
            ],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert report.overall_result == ValidationResult.STALE

    def test_stale_runbook_over_180_days(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested="2024-01-01",
            steps=[
                _step(1, stype=RunbookStepType.DIAGNOSTIC),
                _step(2, stype=RunbookStepType.REMEDIATION),
                _step(3, stype=RunbookStepType.VERIFICATION),
            ],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert report.overall_result == ValidationResult.STALE

    def test_no_steps_gives_incomplete(self):
        g = _graph(_comp("app"))
        rb = _runbook(steps=[])
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert report.overall_result == ValidationResult.INCOMPLETE

    def test_recommendations_no_diagnostic(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            steps=[_step(1, stype=RunbookStepType.REMEDIATION)],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert any("diagnostic" in r.lower() for r in report.recommendations)

    def test_recommendations_no_verification(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            steps=[_step(1, stype=RunbookStepType.DIAGNOSTIC)],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert any("verification" in r.lower() for r in report.recommendations)

    def test_recommendations_no_remediation(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            steps=[_step(1, stype=RunbookStepType.DIAGNOSTIC)],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert any("remediation" in r.lower() for r in report.recommendations)

    def test_confidence_all_valid(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            steps=[
                _step(1, stype=RunbookStepType.DIAGNOSTIC),
                _step(2, stype=RunbookStepType.REMEDIATION),
                _step(3, stype=RunbookStepType.VERIFICATION),
            ],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert report.confidence == 1.0

    def test_confidence_partial(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            steps=[
                _step(1, stype=RunbookStepType.DIAGNOSTIC),
                _step(2, target="missing"),
            ],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert 0.0 < report.confidence < 1.0

    def test_coverage_gaps_in_report(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            steps=[_step(1, target="missing")],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert len(report.coverage_gaps) > 0

    def test_mttr_in_report(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            steps=[_step(1, timeout=600)],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert report.estimated_mttr_minutes == 10.0

    def test_multiple_components(self):
        g = _graph(_comp("app"), _comp("db", ctype=ComponentType.DATABASE))
        rb = _runbook(
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            steps=[
                _step(1, target="app", stype=RunbookStepType.DIAGNOSTIC),
                _step(2, target="db", stype=RunbookStepType.REMEDIATION),
                _step(3, target="app", stype=RunbookStepType.VERIFICATION),
            ],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert report.overall_result == ValidationResult.VALID

    def test_incorrect_overrides_untestable(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            steps=[
                _step(1, timeout=-5),
                _step(2, timeout=7200),
            ],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert report.overall_result == ValidationResult.INCORRECT

    def test_missing_component_overrides_incorrect(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            steps=[
                _step(1, target="missing"),
                _step(2, timeout=-5),
            ],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert report.overall_result == ValidationResult.MISSING_COMPONENT

    def test_staleness_days_in_report(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested="2025-01-01",
            steps=[_step(1, stype=RunbookStepType.DIAGNOSTIC)],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert report.staleness_days > 0


# ---------------------------------------------------------------------------
# RunbookValidationEngine.estimate_mttr tests
# ---------------------------------------------------------------------------


class TestEstimateMttr:
    def test_empty_steps(self):
        rb = _runbook(steps=[])
        engine = RunbookValidationEngine()
        assert engine.estimate_mttr(rb) == 0.0

    def test_single_step(self):
        rb = _runbook(steps=[_step(1, timeout=600)])
        engine = RunbookValidationEngine()
        assert engine.estimate_mttr(rb) == 10.0

    def test_approval_overhead(self):
        rb = _runbook(steps=[_step(1, timeout=300, approval=True)])
        engine = RunbookValidationEngine()
        # 300s step + 300s approval = 600s = 10 min
        assert engine.estimate_mttr(rb) == 10.0

    def test_multiple_steps(self):
        rb = _runbook(
            steps=[
                _step(1, timeout=120),
                _step(2, timeout=180),
                _step(3, timeout=300),
            ]
        )
        engine = RunbookValidationEngine()
        # (120+180+300)/60 = 10 min
        assert engine.estimate_mttr(rb) == 10.0

    def test_multiple_steps_with_approvals(self):
        rb = _runbook(
            steps=[
                _step(1, timeout=60, approval=True),
                _step(2, timeout=60, approval=True),
            ]
        )
        engine = RunbookValidationEngine()
        # (60+300+60+300)/60 = 12 min
        assert engine.estimate_mttr(rb) == 12.0

    def test_no_approval_no_overhead(self):
        rb = _runbook(steps=[_step(1, timeout=60, approval=False)])
        engine = RunbookValidationEngine()
        assert engine.estimate_mttr(rb) == 1.0


# ---------------------------------------------------------------------------
# RunbookValidationEngine.detect_stale_runbooks tests
# ---------------------------------------------------------------------------


class TestDetectStaleRunbooks:
    def test_no_runbooks(self):
        engine = RunbookValidationEngine()
        assert engine.detect_stale_runbooks([]) == []

    def test_fresh_runbook(self):
        rb = _runbook(last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        engine = RunbookValidationEngine()
        assert engine.detect_stale_runbooks([rb]) == []

    def test_stale_runbook(self):
        rb = _runbook(rid="stale-1", last_tested="2020-01-01")
        engine = RunbookValidationEngine()
        result = engine.detect_stale_runbooks([rb])
        assert "stale-1" in result

    def test_custom_max_age(self):
        rb = _runbook(rid="rb-1", last_tested="2026-01-01")
        engine = RunbookValidationEngine()
        # With max_age_days=1, any runbook older than 1 day is stale.
        result = engine.detect_stale_runbooks([rb], max_age_days=1)
        assert "rb-1" in result

    def test_mix_fresh_and_stale(self):
        fresh = _runbook(
            rid="fresh-1",
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        )
        stale = _runbook(rid="stale-1", last_tested="2020-01-01")
        engine = RunbookValidationEngine()
        result = engine.detect_stale_runbooks([fresh, stale])
        assert "stale-1" in result
        assert "fresh-1" not in result

    def test_invalid_date_treated_as_stale(self):
        rb = _runbook(rid="bad-date", last_tested="not-a-date")
        engine = RunbookValidationEngine()
        result = engine.detect_stale_runbooks([rb])
        assert "bad-date" in result

    def test_empty_last_tested_treated_as_stale(self):
        rb = _runbook(rid="empty-date", last_tested="")
        engine = RunbookValidationEngine()
        result = engine.detect_stale_runbooks([rb])
        assert "empty-date" in result


# ---------------------------------------------------------------------------
# RunbookValidationEngine.find_coverage_gaps tests
# ---------------------------------------------------------------------------


class TestFindCoverageGaps:
    def test_no_components(self):
        g = _graph()
        engine = RunbookValidationEngine()
        gaps = engine.find_coverage_gaps(g, [])
        assert gaps == []

    def test_single_component_no_runbooks(self):
        g = _graph(_comp("app"))
        engine = RunbookValidationEngine()
        gaps = engine.find_coverage_gaps(g, [])
        assert len(gaps) > 0

    def test_database_has_expected_scenarios(self):
        g = _graph(_comp("db", ctype=ComponentType.DATABASE))
        engine = RunbookValidationEngine()
        gaps = engine.find_coverage_gaps(g, [])
        scenarios = {gap.failure_scenario for gap in gaps}
        assert "database_failover" in scenarios
        assert "replication_lag" in scenarios

    def test_covered_scenario_not_in_gaps(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            scenario="oom_kill",
            steps=[_step(1, target="app")],
        )
        engine = RunbookValidationEngine()
        gaps = engine.find_coverage_gaps(g, [rb])
        scenarios = {gap.failure_scenario for gap in gaps}
        assert "oom_kill" not in scenarios

    def test_gap_has_component_name(self):
        g = _graph(_comp("app", name="App Server"))
        engine = RunbookValidationEngine()
        gaps = engine.find_coverage_gaps(g, [])
        assert all(gap.component_name == "App Server" for gap in gaps)

    def test_gap_severity_spof(self):
        g = _graph(_comp("app", replicas=1, failover_enabled=False))
        engine = RunbookValidationEngine()
        gaps = engine.find_coverage_gaps(g, [])
        # SPOF with no dependents -> "critical"
        assert all(gap.severity == "critical" for gap in gaps)

    def test_gap_severity_not_spof(self):
        g = _graph(_comp("app", replicas=3, failover_enabled=True))
        engine = RunbookValidationEngine()
        gaps = engine.find_coverage_gaps(g, [])
        assert all(gap.severity == "low" for gap in gaps)

    def test_multiple_components(self):
        g = _graph(
            _comp("app"),
            _comp("db", ctype=ComponentType.DATABASE),
        )
        engine = RunbookValidationEngine()
        gaps = engine.find_coverage_gaps(g, [])
        comp_ids = {gap.component_id for gap in gaps}
        assert "app" in comp_ids
        assert "db" in comp_ids

    def test_custom_component_type(self):
        g = _graph(_comp("custom1", ctype=ComponentType.CUSTOM))
        engine = RunbookValidationEngine()
        gaps = engine.find_coverage_gaps(g, [])
        scenarios = {gap.failure_scenario for gap in gaps}
        assert "unexpected_failure" in scenarios

    def test_severity_with_dependents(self):
        g = _graph(
            _comp("db", replicas=2, ctype=ComponentType.DATABASE),
            _comp("app1"),
            _comp("app2"),
            deps=[
                Dependency(source_id="app1", target_id="db"),
                Dependency(source_id="app2", target_id="db"),
            ],
        )
        engine = RunbookValidationEngine()
        gaps = engine.find_coverage_gaps(g, [])
        db_gaps = [gap for gap in gaps if gap.component_id == "db"]
        assert all(gap.severity == "high" for gap in db_gaps)


# ---------------------------------------------------------------------------
# RunbookValidationEngine.suggest_runbook tests
# ---------------------------------------------------------------------------


class TestSuggestRunbook:
    def test_generates_runbook(self):
        g = _graph(_comp("app"))
        engine = RunbookValidationEngine()
        rb = engine.suggest_runbook(g, "oom_kill")
        assert isinstance(rb, RunbookV2)
        assert rb.scenario == "oom_kill"

    def test_has_diagnostic_step(self):
        g = _graph(_comp("app"))
        engine = RunbookValidationEngine()
        rb = engine.suggest_runbook(g, "oom_kill")
        types = [s.step_type for s in rb.steps]
        assert RunbookStepType.DIAGNOSTIC in types

    def test_has_notification_step(self):
        g = _graph(_comp("app"))
        engine = RunbookValidationEngine()
        rb = engine.suggest_runbook(g, "disk_full")
        types = [s.step_type for s in rb.steps]
        assert RunbookStepType.NOTIFICATION in types

    def test_has_remediation_step(self):
        g = _graph(_comp("app"))
        engine = RunbookValidationEngine()
        rb = engine.suggest_runbook(g, "oom_kill")
        types = [s.step_type for s in rb.steps]
        assert RunbookStepType.REMEDIATION in types

    def test_has_verification_step(self):
        g = _graph(_comp("app"))
        engine = RunbookValidationEngine()
        rb = engine.suggest_runbook(g, "oom_kill")
        types = [s.step_type for s in rb.steps]
        assert RunbookStepType.VERIFICATION in types

    def test_has_rollback_step(self):
        g = _graph(_comp("app"))
        engine = RunbookValidationEngine()
        rb = engine.suggest_runbook(g, "oom_kill")
        types = [s.step_type for s in rb.steps]
        assert RunbookStepType.ROLLBACK in types

    def test_rollback_requires_approval(self):
        g = _graph(_comp("app"))
        engine = RunbookValidationEngine()
        rb = engine.suggest_runbook(g, "oom_kill")
        rollback_steps = [s for s in rb.steps if s.step_type == RunbookStepType.ROLLBACK]
        assert all(s.requires_approval for s in rollback_steps)

    def test_multiple_components_remediation_per_component(self):
        g = _graph(_comp("app"), _comp("db", ctype=ComponentType.DATABASE))
        engine = RunbookValidationEngine()
        rb = engine.suggest_runbook(g, "cascade_failure")
        remediation = [s for s in rb.steps if s.step_type == RunbookStepType.REMEDIATION]
        targets = {s.target_component_id for s in remediation}
        assert "app" in targets
        assert "db" in targets

    def test_id_contains_scenario(self):
        g = _graph(_comp("app"))
        engine = RunbookValidationEngine()
        rb = engine.suggest_runbook(g, "disk full")
        assert "disk-full" in rb.id

    def test_owner_is_auto(self):
        g = _graph(_comp("app"))
        engine = RunbookValidationEngine()
        rb = engine.suggest_runbook(g, "test")
        assert rb.owner == "auto-generated"

    def test_last_tested_is_today(self):
        g = _graph(_comp("app"))
        engine = RunbookValidationEngine()
        rb = engine.suggest_runbook(g, "test")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert rb.last_tested == today

    def test_step_numbers_sequential(self):
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        engine = RunbookValidationEngine()
        rb = engine.suggest_runbook(g, "test")
        nums = [s.step_number for s in rb.steps]
        assert nums == list(range(1, len(rb.steps) + 1))


# ---------------------------------------------------------------------------
# RunbookValidationEngine.validate_escalation_path tests
# ---------------------------------------------------------------------------


class TestValidateEscalationPath:
    def test_no_escalation_no_notification(self):
        rb = _runbook(steps=[_step(1, stype=RunbookStepType.REMEDIATION)])
        engine = RunbookValidationEngine()
        ev = engine.validate_escalation_path(rb)
        assert ev.has_escalation is False
        assert ev.has_notification is False
        assert ev.is_valid is False
        assert len(ev.issues) == 2

    def test_has_escalation_only(self):
        rb = _runbook(steps=[
            _step(1, stype=RunbookStepType.DIAGNOSTIC),
            _step(2, stype=RunbookStepType.ESCALATION),
        ])
        engine = RunbookValidationEngine()
        ev = engine.validate_escalation_path(rb)
        assert ev.has_escalation is True
        assert ev.has_notification is False
        assert ev.is_valid is False

    def test_has_notification_only(self):
        rb = _runbook(steps=[
            _step(1, stype=RunbookStepType.NOTIFICATION),
            _step(2, stype=RunbookStepType.REMEDIATION),
        ])
        engine = RunbookValidationEngine()
        ev = engine.validate_escalation_path(rb)
        assert ev.has_notification is True
        assert ev.has_escalation is False
        assert ev.is_valid is False

    def test_valid_escalation_path(self):
        rb = _runbook(steps=[
            _step(1, stype=RunbookStepType.DIAGNOSTIC),
            _step(2, stype=RunbookStepType.NOTIFICATION),
            _step(3, stype=RunbookStepType.ESCALATION),
        ])
        engine = RunbookValidationEngine()
        ev = engine.validate_escalation_path(rb)
        assert ev.is_valid is True
        assert ev.issues == []

    def test_escalation_before_notification(self):
        rb = _runbook(steps=[
            _step(1, stype=RunbookStepType.ESCALATION),
            _step(2, stype=RunbookStepType.NOTIFICATION),
        ])
        engine = RunbookValidationEngine()
        ev = engine.validate_escalation_path(rb)
        assert ev.is_valid is False
        assert any("before notification" in i.lower() for i in ev.issues)

    def test_escalation_as_first_step(self):
        rb = _runbook(steps=[
            _step(1, stype=RunbookStepType.ESCALATION),
            _step(2, stype=RunbookStepType.NOTIFICATION),
        ])
        engine = RunbookValidationEngine()
        ev = engine.validate_escalation_path(rb)
        assert any("first step" in i.lower() for i in ev.issues)

    def test_escalation_step_numbers_listed(self):
        rb = _runbook(steps=[
            _step(1, stype=RunbookStepType.NOTIFICATION),
            _step(2, stype=RunbookStepType.ESCALATION),
            _step(3, stype=RunbookStepType.ESCALATION),
        ])
        engine = RunbookValidationEngine()
        ev = engine.validate_escalation_path(rb)
        assert ev.escalation_steps == [2, 3]

    def test_notification_step_numbers_listed(self):
        rb = _runbook(steps=[
            _step(1, stype=RunbookStepType.NOTIFICATION),
            _step(2, stype=RunbookStepType.NOTIFICATION),
            _step(3, stype=RunbookStepType.ESCALATION),
        ])
        engine = RunbookValidationEngine()
        ev = engine.validate_escalation_path(rb)
        assert ev.notification_steps == [1, 2]

    def test_empty_runbook(self):
        rb = _runbook(steps=[])
        engine = RunbookValidationEngine()
        ev = engine.validate_escalation_path(rb)
        assert ev.has_escalation is False
        assert ev.has_notification is False
        assert ev.is_valid is False


# ---------------------------------------------------------------------------
# RunbookValidationEngine.compare_runbooks tests
# ---------------------------------------------------------------------------


class TestCompareRunbooks:
    def test_identical_runbooks(self):
        rb = _runbook(steps=[_step(1)])
        engine = RunbookValidationEngine()
        comp = engine.compare_runbooks(rb, rb)
        assert comp.is_identical is True

    def test_different_name(self):
        a = _runbook(rid="a", name="Alpha")
        b = _runbook(rid="b", name="Beta")
        engine = RunbookValidationEngine()
        comp = engine.compare_runbooks(a, b)
        assert comp.is_identical is False
        fields = {d.field for d in comp.differences}
        assert "name" in fields

    def test_different_scenario(self):
        a = _runbook(rid="a", scenario="oom")
        b = _runbook(rid="b", scenario="disk_full")
        engine = RunbookValidationEngine()
        comp = engine.compare_runbooks(a, b)
        fields = {d.field for d in comp.differences}
        assert "scenario" in fields

    def test_different_owner(self):
        a = _runbook(rid="a", owner="team-a")
        b = _runbook(rid="b", owner="team-b")
        engine = RunbookValidationEngine()
        comp = engine.compare_runbooks(a, b)
        fields = {d.field for d in comp.differences}
        assert "owner" in fields

    def test_different_severity(self):
        a = _runbook(rid="a", severity="high")
        b = _runbook(rid="b", severity="critical")
        engine = RunbookValidationEngine()
        comp = engine.compare_runbooks(a, b)
        fields = {d.field for d in comp.differences}
        assert "severity" in fields

    def test_different_last_tested(self):
        a = _runbook(rid="a", last_tested="2025-01-01")
        b = _runbook(rid="b", last_tested="2026-01-01")
        engine = RunbookValidationEngine()
        comp = engine.compare_runbooks(a, b)
        fields = {d.field for d in comp.differences}
        assert "last_tested" in fields

    def test_step_added(self):
        a = _runbook(rid="a", steps=[_step(1)])
        b = _runbook(rid="b", steps=[_step(1), _step(2)])
        engine = RunbookValidationEngine()
        comp = engine.compare_runbooks(a, b)
        assert 2 in comp.steps_added

    def test_step_removed(self):
        a = _runbook(rid="a", steps=[_step(1), _step(2)])
        b = _runbook(rid="b", steps=[_step(1)])
        engine = RunbookValidationEngine()
        comp = engine.compare_runbooks(a, b)
        assert 2 in comp.steps_removed

    def test_step_modified(self):
        a = _runbook(rid="a", steps=[_step(1, desc="Do X")])
        b = _runbook(rid="b", steps=[_step(1, desc="Do Y")])
        engine = RunbookValidationEngine()
        comp = engine.compare_runbooks(a, b)
        assert 1 in comp.steps_modified

    def test_ids_in_comparison(self):
        a = _runbook(rid="alpha")
        b = _runbook(rid="beta")
        engine = RunbookValidationEngine()
        comp = engine.compare_runbooks(a, b)
        assert comp.runbook_a_id == "alpha"
        assert comp.runbook_b_id == "beta"

    def test_no_steps_identical(self):
        a = _runbook(rid="a", steps=[])
        b = _runbook(rid="b", steps=[])
        engine = RunbookValidationEngine()
        comp = engine.compare_runbooks(a, b)
        assert comp.steps_added == []
        assert comp.steps_removed == []
        assert comp.steps_modified == []

    def test_multiple_differences(self):
        a = _runbook(rid="a", name="A", owner="x", steps=[_step(1), _step(3)])
        b = _runbook(rid="b", name="B", owner="y", steps=[_step(2), _step(3, desc="Changed")])
        engine = RunbookValidationEngine()
        comp = engine.compare_runbooks(a, b)
        assert comp.is_identical is False
        assert len(comp.differences) >= 2


# ---------------------------------------------------------------------------
# Integration / edge-case tests
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_suggested_runbook_validates_clean(self):
        """A suggested runbook should validate as VALID against the same graph."""
        g = _graph(_comp("app"), _comp("db", ctype=ComponentType.DATABASE))
        engine = RunbookValidationEngine()
        suggested = engine.suggest_runbook(g, "cascade_failure")
        report = engine.validate_runbook(g, suggested)
        assert report.overall_result == ValidationResult.VALID
        assert report.confidence == 1.0

    def test_suggested_runbook_has_no_coverage_gaps_for_self(self):
        g = _graph(_comp("app"))
        engine = RunbookValidationEngine()
        suggested = engine.suggest_runbook(g, "oom_kill")
        report = engine.validate_runbook(g, suggested)
        assert len(report.coverage_gaps) == 0

    def test_stale_detection_matches_validate(self):
        """detect_stale_runbooks and validate_runbook should agree on staleness."""
        g = _graph(_comp("app"))
        rb = _runbook(
            rid="old",
            last_tested="2020-01-01",
            steps=[
                _step(1, stype=RunbookStepType.DIAGNOSTIC),
                _step(2, stype=RunbookStepType.REMEDIATION),
                _step(3, stype=RunbookStepType.VERIFICATION),
            ],
        )
        engine = RunbookValidationEngine()
        stale_ids = engine.detect_stale_runbooks([rb])
        report = engine.validate_runbook(g, rb)
        assert "old" in stale_ids
        assert report.overall_result == ValidationResult.STALE

    def test_escalation_valid_on_suggested_with_escalation(self):
        """Adding escalation to a suggested runbook should pass escalation check."""
        g = _graph(_comp("app"))
        engine = RunbookValidationEngine()
        suggested = engine.suggest_runbook(g, "test")
        # Add notification + escalation steps.
        suggested.steps.insert(
            1,
            _step(
                num=max(s.step_number for s in suggested.steps) + 1,
                stype=RunbookStepType.NOTIFICATION,
            ),
        )
        suggested.steps.append(
            _step(
                num=max(s.step_number for s in suggested.steps) + 1,
                stype=RunbookStepType.ESCALATION,
            ),
        )
        ev = engine.validate_escalation_path(suggested)
        assert ev.has_escalation is True
        assert ev.has_notification is True

    def test_large_graph_coverage_gaps(self):
        """Many components should produce many gaps when no runbooks exist."""
        comps = [_comp(f"c{i}", ctype=ComponentType.APP_SERVER) for i in range(20)]
        g = _graph(*comps)
        engine = RunbookValidationEngine()
        gaps = engine.find_coverage_gaps(g, [])
        # APP_SERVER has 3 scenarios per component.
        assert len(gaps) == 20 * 3

    def test_compare_same_object(self):
        rb = _runbook(steps=[_step(1), _step(2)])
        engine = RunbookValidationEngine()
        comp = engine.compare_runbooks(rb, rb)
        assert comp.is_identical is True

    def test_full_workflow(self):
        """Full workflow: suggest, validate, check escalation, find gaps."""
        g = _graph(
            _comp("lb", ctype=ComponentType.LOAD_BALANCER),
            _comp("app"),
            _comp("db", ctype=ComponentType.DATABASE),
            deps=[
                Dependency(source_id="lb", target_id="app"),
                Dependency(source_id="app", target_id="db"),
            ],
        )
        engine = RunbookValidationEngine()

        # Suggest.
        rb = engine.suggest_runbook(g, "cascade_failure")
        assert len(rb.steps) > 0

        # Validate.
        report = engine.validate_runbook(g, rb)
        assert report.overall_result == ValidationResult.VALID

        # MTTR.
        mttr = engine.estimate_mttr(rb)
        assert mttr > 0

        # Coverage gaps (partial coverage).
        gaps = engine.find_coverage_gaps(g, [rb])
        assert len(gaps) > 0  # Can't cover all typed scenarios with one runbook.

        # Stale detection.
        stale = engine.detect_stale_runbooks([rb])
        assert stale == []

    def test_engine_is_stateless(self):
        """Multiple calls to the same engine should be independent."""
        engine = RunbookValidationEngine()
        g1 = _graph(_comp("a"))
        g2 = _graph(_comp("b"))
        r1 = engine.suggest_runbook(g1, "test1")
        r2 = engine.suggest_runbook(g2, "test2")
        assert r1.scenario == "test1"
        assert r2.scenario == "test2"
        # Ensure no state leak.
        assert r1.steps[0].target_component_id == "a"
        assert r2.steps[0].target_component_id == "b"

    def test_validate_with_dependencies(self):
        g = _graph(
            _comp("app"),
            _comp("db", ctype=ComponentType.DATABASE),
            deps=[Dependency(source_id="app", target_id="db")],
        )
        rb = _runbook(
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            steps=[
                _step(1, target="app", stype=RunbookStepType.DIAGNOSTIC),
                _step(2, target="db", stype=RunbookStepType.REMEDIATION),
                _step(3, target="app", stype=RunbookStepType.VERIFICATION),
            ],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert report.overall_result == ValidationResult.VALID

    def test_gap_severity_with_many_dependents(self):
        """Component with 3+ dependents should be critical even if not SPOF."""
        g = _graph(
            _comp("db", replicas=3, ctype=ComponentType.DATABASE),
            _comp("a1"), _comp("a2"), _comp("a3"),
            deps=[
                Dependency(source_id="a1", target_id="db"),
                Dependency(source_id="a2", target_id="db"),
                Dependency(source_id="a3", target_id="db"),
            ],
        )
        engine = RunbookValidationEngine()
        gaps = engine.find_coverage_gaps(g, [])
        db_gaps = [g for g in gaps if g.component_id == "db"]
        assert all(gap.severity == "critical" for gap in db_gaps)

    def test_gap_severity_medium_one_dependent(self):
        g = _graph(
            _comp("db", replicas=3, ctype=ComponentType.DATABASE),
            _comp("app"),
            deps=[Dependency(source_id="app", target_id="db")],
        )
        engine = RunbookValidationEngine()
        gaps = engine.find_coverage_gaps(g, [])
        db_gaps = [g for g in gaps if g.component_id == "db"]
        assert all(gap.severity == "medium" for gap in db_gaps)

    def test_validation_report_runbook_id(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            rid="my-runbook-42",
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            steps=[_step(1)],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert report.runbook_id == "my-runbook-42"

    def test_stale_recommendation_text(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested="2024-01-01",
            steps=[_step(1)],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert any("stale" in r.lower() for r in report.recommendations)

    def test_timeout_boundary_3600(self):
        """Timeout of exactly 3600s should be valid (not untestable)."""
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            steps=[_step(1, timeout=3600)],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert report.step_validations[0].result == ValidationResult.VALID

    def test_timeout_boundary_3601(self):
        """Timeout of 3601s should be untestable."""
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            steps=[_step(1, timeout=3601)],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert report.step_validations[0].result == ValidationResult.UNTESTABLE

    def test_dns_component_scenarios(self):
        g = _graph(_comp("dns1", ctype=ComponentType.DNS))
        engine = RunbookValidationEngine()
        gaps = engine.find_coverage_gaps(g, [])
        scenarios = {gap.failure_scenario for gap in gaps}
        assert "dns_resolution_failure" in scenarios
        assert "ttl_misconfiguration" in scenarios

    def test_queue_component_scenarios(self):
        g = _graph(_comp("q1", ctype=ComponentType.QUEUE))
        engine = RunbookValidationEngine()
        gaps = engine.find_coverage_gaps(g, [])
        scenarios = {gap.failure_scenario for gap in gaps}
        assert "message_backlog" in scenarios
        assert "dead_letter_overflow" in scenarios

    def test_cache_component_scenarios(self):
        g = _graph(_comp("cache1", ctype=ComponentType.CACHE))
        engine = RunbookValidationEngine()
        gaps = engine.find_coverage_gaps(g, [])
        scenarios = {gap.failure_scenario for gap in gaps}
        assert "cache_stampede" in scenarios
        assert "memory_overflow" in scenarios

    def test_storage_component_scenarios(self):
        g = _graph(_comp("s1", ctype=ComponentType.STORAGE))
        engine = RunbookValidationEngine()
        gaps = engine.find_coverage_gaps(g, [])
        scenarios = {gap.failure_scenario for gap in gaps}
        assert "disk_full" in scenarios
        assert "io_throttle" in scenarios

    def test_external_api_scenarios(self):
        g = _graph(_comp("ext1", ctype=ComponentType.EXTERNAL_API))
        engine = RunbookValidationEngine()
        gaps = engine.find_coverage_gaps(g, [])
        scenarios = {gap.failure_scenario for gap in gaps}
        assert "upstream_timeout" in scenarios
        assert "rate_limiting" in scenarios

    def test_load_balancer_scenarios(self):
        g = _graph(_comp("lb1", ctype=ComponentType.LOAD_BALANCER))
        engine = RunbookValidationEngine()
        gaps = engine.find_coverage_gaps(g, [])
        scenarios = {gap.failure_scenario for gap in gaps}
        assert "routing_failure" in scenarios
        assert "health_check_misconfiguration" in scenarios

    def test_web_server_scenarios(self):
        g = _graph(_comp("ws1", ctype=ComponentType.WEB_SERVER))
        engine = RunbookValidationEngine()
        gaps = engine.find_coverage_gaps(g, [])
        scenarios = {gap.failure_scenario for gap in gaps}
        assert "connection_limit" in scenarios
        assert "tls_expiry" in scenarios

    def test_compare_with_step_type_change(self):
        a = _runbook(rid="a", steps=[_step(1, stype=RunbookStepType.DIAGNOSTIC)])
        b = _runbook(rid="b", steps=[_step(1, stype=RunbookStepType.REMEDIATION)])
        engine = RunbookValidationEngine()
        comp = engine.compare_runbooks(a, b)
        assert 1 in comp.steps_modified
        assert comp.is_identical is False

    def test_mttr_rounding(self):
        rb = _runbook(steps=[_step(1, timeout=100)])
        engine = RunbookValidationEngine()
        mttr = engine.estimate_mttr(rb)
        assert mttr == round(100 / 60, 2)

    def test_confidence_zero_on_all_missing(self):
        g = _graph(_comp("app"))
        rb = _runbook(
            last_tested=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            steps=[
                _step(1, target="x"),
                _step(2, target="y"),
            ],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert report.confidence == 0.0

    def test_detect_stale_with_large_max_age(self):
        rb = _runbook(rid="rb-1", last_tested="2020-01-01")
        engine = RunbookValidationEngine()
        result = engine.detect_stale_runbooks([rb], max_age_days=999999)
        assert result == []

    def test_coverage_gap_fuzzy_match_by_scenario_name(self):
        """When a runbook scenario name matches a coverage scenario, it should not be a gap.

        The runbook's steps target a *different* component so (comp_id, scenario) is
        not in the exact-match set, but the scenario name is in covered_scenarios.
        """
        g = _graph(
            _comp("app"),
            _comp("db", ctype=ComponentType.DATABASE),
        )
        # Runbook targets "db" but scenario is "oom_kill" (an APP_SERVER scenario).
        rb = _runbook(scenario="oom_kill", steps=[_step(1, target="db")])
        engine = RunbookValidationEngine()
        gaps = engine.find_coverage_gaps(g, [rb])
        app_scenarios = {gap.failure_scenario for gap in gaps if gap.component_id == "app"}
        assert "oom_kill" not in app_scenarios

    def test_severity_from_dependents_spof_with_two_dependents(self):
        """SPOF with 2+ dependents -> critical."""
        g = _graph(
            _comp("db", replicas=1, failover_enabled=False, ctype=ComponentType.DATABASE),
            _comp("a1"),
            _comp("a2"),
            deps=[
                Dependency(source_id="a1", target_id="db"),
                Dependency(source_id="a2", target_id="db"),
            ],
        )
        engine = RunbookValidationEngine()
        gaps = engine.find_coverage_gaps(g, [])
        db_gaps = [gap for gap in gaps if gap.component_id == "db"]
        assert all(gap.severity == "critical" for gap in db_gaps)

    def test_overall_stale_between_90_and_180(self):
        """Runbook that is 91-180 days stale with all valid steps should be STALE."""
        g = _graph(_comp("app"))
        # Pick a date ~120 days ago.
        from datetime import timedelta
        dt = datetime.now(timezone.utc) - timedelta(days=120)
        rb = _runbook(
            last_tested=dt.strftime("%Y-%m-%d"),
            steps=[
                _step(1, stype=RunbookStepType.DIAGNOSTIC),
                _step(2, stype=RunbookStepType.REMEDIATION),
                _step(3, stype=RunbookStepType.VERIFICATION),
            ],
        )
        engine = RunbookValidationEngine()
        report = engine.validate_runbook(g, rb)
        assert report.overall_result == ValidationResult.STALE


# ===========================================================================
# Legacy RunbookValidator (v1) tests
# ===========================================================================

def _v1_step(
    order: int = 1,
    desc: str = "step",
    automated: bool = False,
    time: float = 10.0,
    approval: bool = False,
) -> RecoveryStep:
    return RecoveryStep(
        order=order,
        description=desc,
        is_automated=automated,
        estimated_time_minutes=time,
        requires_approval=approval,
    )


def _v1_runbook(
    scenario_id: str = "app:out of memory",
    title: str = "OOM runbook",
    component_id: str = "app",
    steps: list[RecoveryStep] | None = None,
    last_tested: str | None = "2026-01-01",
    owner: str = "team-a",
    status: RunbookStatus = RunbookStatus.COMPLETE,
    total_time: float = 30.0,
) -> RunbookV1:
    return RunbookV1(
        scenario_id=scenario_id,
        title=title,
        component_id=component_id,
        steps=steps if steps is not None else [_v1_step()],
        last_tested=last_tested,
        owner=owner,
        status=status,
        estimated_total_time_minutes=total_time,
    )


class TestRunbookStatusEnum:
    def test_complete(self):
        assert RunbookStatus.COMPLETE == "complete"

    def test_partial(self):
        assert RunbookStatus.PARTIAL == "partial"

    def test_missing(self):
        assert RunbookStatus.MISSING == "missing"

    def test_outdated(self):
        assert RunbookStatus.OUTDATED == "outdated"


class TestRecoveryStep:
    def test_fields(self):
        s = _v1_step(order=3, desc="restart", automated=True, time=5.0, approval=True)
        assert s.order == 3
        assert s.description == "restart"
        assert s.is_automated is True
        assert s.estimated_time_minutes == 5.0
        assert s.requires_approval is True


class TestRunbookV1Model:
    def test_fields(self):
        rb = _v1_runbook()
        assert rb.scenario_id == "app:out of memory"
        assert rb.title == "OOM runbook"
        assert rb.component_id == "app"
        assert rb.status == RunbookStatus.COMPLETE

    def test_last_tested_none(self):
        rb = _v1_runbook(last_tested=None)
        assert rb.last_tested is None


class TestRunbookGapModel:
    def test_fields(self):
        g = RunbookGap(
            scenario_description="oom on app",
            component_id="app",
            component_name="App Server",
            severity="critical",
            reason="No runbook",
            suggested_steps=["Restart"],
        )
        assert g.severity == "critical"
        assert g.suggested_steps == ["Restart"]


class TestRunbookValidationReportV1Model:
    def test_fields(self):
        r = RunbookValidationReportV1(
            total_scenarios=10,
            covered_scenarios=7,
            coverage_percent=70.0,
            completeness_score=80.0,
            gaps=[],
            existing_runbooks=[],
            recommendations=["Test more"],
            mean_recovery_time_minutes=15.0,
        )
        assert r.total_scenarios == 10
        assert r.coverage_percent == 70.0


class TestRunbookValidatorV1:
    """Tests for the legacy RunbookValidator class."""

    def _build_graph(self) -> InfraGraph:
        g = InfraGraph()
        g.add_component(_comp("app", ctype=ComponentType.APP_SERVER, replicas=1))
        g.add_component(_comp("db", ctype=ComponentType.DATABASE, replicas=2))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        return g

    def test_validate_no_runbooks(self):
        g = self._build_graph()
        v = RunbookValidator(g)
        report = v.validate()
        assert report.total_scenarios > 0
        assert report.covered_scenarios == 0
        assert len(report.gaps) > 0

    def test_validate_empty_graph(self):
        g = _graph()
        v = RunbookValidator(g)
        report = v.validate()
        assert report.total_scenarios == 0
        assert report.coverage_percent == 100.0

    def test_validate_with_complete_runbook(self):
        g = self._build_graph()
        rb = _v1_runbook(
            scenario_id="app:out of memory",
            component_id="app",
            status=RunbookStatus.COMPLETE,
        )
        v = RunbookValidator(g)
        report = v.validate([rb])
        assert report.covered_scenarios >= 1

    def test_validate_with_outdated_runbook_not_covered(self):
        g = self._build_graph()
        rb = _v1_runbook(
            scenario_id="app:out of memory",
            status=RunbookStatus.OUTDATED,
        )
        v = RunbookValidator(g)
        report = v.validate([rb])
        # Outdated runbook should still be a gap.
        assert any("outdated" in gap.reason.lower() for gap in report.gaps)

    def test_validate_with_missing_status_not_covered(self):
        g = self._build_graph()
        rb = _v1_runbook(
            scenario_id="app:out of memory",
            status=RunbookStatus.MISSING,
        )
        v = RunbookValidator(g)
        report = v.validate([rb])
        assert any("missing" in gap.reason.lower() for gap in report.gaps)

    def test_fuzzy_match_by_title(self):
        g = self._build_graph()
        rb = _v1_runbook(
            scenario_id="custom-id",
            component_id="app",
            title="Handle Out Of Memory",
            status=RunbookStatus.COMPLETE,
        )
        v = RunbookValidator(g)
        report = v.validate([rb])
        assert report.covered_scenarios >= 1

    def test_fuzzy_match_outdated_not_covered(self):
        g = self._build_graph()
        rb = _v1_runbook(
            scenario_id="custom-id",
            component_id="app",
            title="Handle Out Of Memory",
            status=RunbookStatus.OUTDATED,
        )
        v = RunbookValidator(g)
        report = v.validate([rb])
        # Even with fuzzy match, outdated = not covered.
        gap_scenarios = [gap.scenario_description for gap in report.gaps]
        assert any("out of memory" in s for s in gap_scenarios)

    def test_generate_required_scenarios(self):
        g = self._build_graph()
        v = RunbookValidator(g)
        gaps = v.generate_required_scenarios()
        assert len(gaps) > 0
        assert all(isinstance(g, RunbookGap) for g in gaps)

    def test_compute_severity_critical_spof_high_deps(self):
        assert RunbookValidator._compute_severity(2, True) == "critical"

    def test_compute_severity_critical_spof_only(self):
        assert RunbookValidator._compute_severity(0, True) == "critical"

    def test_compute_severity_critical_many_deps(self):
        assert RunbookValidator._compute_severity(3, False) == "critical"

    def test_compute_severity_high(self):
        assert RunbookValidator._compute_severity(2, False) == "high"

    def test_compute_severity_medium(self):
        assert RunbookValidator._compute_severity(1, False) == "medium"

    def test_compute_severity_low(self):
        assert RunbookValidator._compute_severity(0, False) == "low"

    def test_calculate_completeness_no_runbooks(self):
        g = self._build_graph()
        v = RunbookValidator(g)
        assert v._calculate_completeness([]) == 0.0

    def test_calculate_completeness_complete_with_steps(self):
        g = self._build_graph()
        v = RunbookValidator(g)
        rb = _v1_runbook(
            status=RunbookStatus.COMPLETE,
            steps=[_v1_step(i, automated=True) for i in range(6)],
            last_tested="2026-01-01",
        )
        score = v._calculate_completeness([rb])
        assert score == 100.0

    def test_calculate_completeness_partial(self):
        g = self._build_graph()
        v = RunbookValidator(g)
        rb = _v1_runbook(status=RunbookStatus.PARTIAL, steps=[_v1_step()], last_tested=None)
        score = v._calculate_completeness([rb])
        assert 0.0 < score < 100.0

    def test_calculate_completeness_missing_status_no_steps(self):
        g = self._build_graph()
        v = RunbookValidator(g)
        rb = _v1_runbook(status=RunbookStatus.MISSING, steps=[], last_tested=None)
        score = v._calculate_completeness([rb])
        # MISSING status = 0 points, no steps = 0 points, no automation, no testing = 0
        assert score == 0.0

    def test_calculate_completeness_missing_status_with_step(self):
        g = self._build_graph()
        v = RunbookValidator(g)
        rb = _v1_runbook(status=RunbookStatus.MISSING, steps=[_v1_step()], last_tested=None)
        score = v._calculate_completeness([rb])
        # 0 (status) + 5.0 (1/5*25) + 0 (not automated) + 0 (not tested) = 5.0
        assert score == 5.0

    def test_calculate_completeness_outdated(self):
        g = self._build_graph()
        v = RunbookValidator(g)
        rb = _v1_runbook(status=RunbookStatus.OUTDATED, steps=[_v1_step()], last_tested=None)
        score = v._calculate_completeness([rb])
        assert 0.0 < score < 50.0

    def test_estimate_mean_recovery(self):
        g = self._build_graph()
        v = RunbookValidator(g)
        rbs = [_v1_runbook(total_time=20.0), _v1_runbook(total_time=40.0)]
        assert v._estimate_mean_recovery(rbs) == 30.0

    def test_estimate_mean_recovery_empty(self):
        g = self._build_graph()
        v = RunbookValidator(g)
        assert v._estimate_mean_recovery([]) == 0.0

    def test_estimate_mean_recovery_zero_times(self):
        g = self._build_graph()
        v = RunbookValidator(g)
        rbs = [_v1_runbook(total_time=0.0)]
        assert v._estimate_mean_recovery(rbs) == 0.0

    def test_recommendations_low_coverage(self):
        g = self._build_graph()
        v = RunbookValidator(g)
        report = v.validate([])
        assert any("coverage" in r.lower() for r in report.recommendations)

    def test_recommendations_critical_gaps(self):
        g = self._build_graph()
        v = RunbookValidator(g)
        report = v.validate([])
        assert any("critical" in r.lower() for r in report.recommendations)

    def test_recommendations_outdated_runbook(self):
        g = self._build_graph()
        v = RunbookValidator(g)
        rb = _v1_runbook(
            scenario_id="app:out of memory",
            title="OOM Recovery",
            status=RunbookStatus.OUTDATED,
        )
        report = v.validate([rb])
        assert any("outdated" in r.lower() for r in report.recommendations)

    def test_recommendations_partial_runbook(self):
        g = self._build_graph()
        v = RunbookValidator(g)
        rb = _v1_runbook(
            scenario_id="app:out of memory",
            title="OOM Partial",
            status=RunbookStatus.PARTIAL,
        )
        report = v.validate([rb])
        assert any("partial" in r.lower() for r in report.recommendations)

    def test_recommendations_untested(self):
        g = self._build_graph()
        v = RunbookValidator(g)
        rb = _v1_runbook(
            scenario_id="app:out of memory",
            last_tested=None,
        )
        report = v.validate([rb])
        assert any("untested" in r.lower() for r in report.recommendations)

    def test_recommendations_low_automation(self):
        g = self._build_graph()
        v = RunbookValidator(g)
        rb = _v1_runbook(
            scenario_id="app:out of memory",
            steps=[_v1_step(i, automated=False) for i in range(5)],
        )
        report = v.validate([rb])
        assert any("automation" in r.lower() for r in report.recommendations)

    def test_recommendations_low_completeness(self):
        g = self._build_graph()
        v = RunbookValidator(g)
        rb = _v1_runbook(
            scenario_id="app:out of memory",
            status=RunbookStatus.PARTIAL,
            steps=[_v1_step()],
            last_tested=None,
        )
        report = v.validate([rb])
        assert any("completeness" in r.lower() for r in report.recommendations)

    def test_suggest_recovery_steps_known_scenario(self):
        g = self._build_graph()
        v = RunbookValidator(g)
        steps = v._suggest_recovery_steps("app", "out of memory")
        assert len(steps) > 0
        assert any("memory" in s.lower() for s in steps)

    def test_suggest_recovery_steps_unknown_scenario(self):
        g = self._build_graph()
        v = RunbookValidator(g)
        steps = v._suggest_recovery_steps("app", "alien_invasion")
        assert len(steps) > 0
        assert any("alien_invasion" in s.lower() for s in steps)

    def test_coverage_percent_below_80(self):
        """Coverage between 50% and 80% should produce a specific recommendation."""
        g = _graph()
        g.add_component(_comp("app", ctype=ComponentType.APP_SERVER, replicas=1))
        v = RunbookValidator(g)
        # APP_SERVER has 3 scenarios; cover 2 of 3 -> 66%.
        rbs = [
            _v1_runbook(scenario_id="app:out of memory", status=RunbookStatus.COMPLETE),
            _v1_runbook(scenario_id="app:thread exhaustion", status=RunbookStatus.COMPLETE),
        ]
        report = v.validate(rbs)
        assert report.coverage_percent > 50.0
        assert report.coverage_percent < 80.0
        assert any("below target" in r.lower() for r in report.recommendations)

    def test_all_scenarios_covered(self):
        g = _graph()
        g.add_component(_comp("app", ctype=ComponentType.APP_SERVER, replicas=1))
        v = RunbookValidator(g)
        rbs = [
            _v1_runbook(scenario_id="app:out of memory", status=RunbookStatus.COMPLETE),
            _v1_runbook(scenario_id="app:thread exhaustion", status=RunbookStatus.COMPLETE),
            _v1_runbook(scenario_id="app:dependency timeout", status=RunbookStatus.COMPLETE),
        ]
        report = v.validate(rbs)
        assert report.coverage_percent == 100.0
        assert report.covered_scenarios == 3
        assert len(report.gaps) == 0

    def test_multiple_component_types(self):
        g = _graph()
        g.add_component(_comp("ws", ctype=ComponentType.WEB_SERVER, replicas=1))
        g.add_component(_comp("cache", ctype=ComponentType.CACHE, replicas=1))
        v = RunbookValidator(g)
        report = v.validate([])
        # WEB_SERVER has 2, CACHE has 2 -> total 4 scenarios.
        assert report.total_scenarios == 4

    def test_calculate_completeness_few_steps(self):
        g = self._build_graph()
        v = RunbookValidator(g)
        rb = _v1_runbook(
            status=RunbookStatus.COMPLETE,
            steps=[_v1_step(1), _v1_step(2), _v1_step(3)],
            last_tested="2026-01-01",
        )
        score = v._calculate_completeness([rb])
        # 40 (status) + 15 (3/5 * 25) + 0 (no automation) + 15 (tested) = 70
        assert score == 70.0

    def test_identify_critical_scenarios_with_dependents(self):
        g = self._build_graph()
        v = RunbookValidator(g)
        scenarios = v._identify_critical_scenarios()
        # Each scenario should have comp_id, description, severity.
        for comp_id, desc, severity in scenarios:
            assert severity in ("critical", "high", "medium", "low")
