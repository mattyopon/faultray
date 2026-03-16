"""Tests for the Configuration Drift Reconciler Engine.

Comprehensive test suite covering DriftSource/ReconciliationAction enums,
ConfigField/ReconciliationStep/DriftAnalysis/ReconciliationResult/DriftReport
models, ConfigDriftReconcilerEngine methods (analyze_drift, detect_field_drift,
recommend_reconciliation, simulate_reconciliation, calculate_drift_risk,
generate_drift_report, find_safe_reconciliation_order), edge cases, and
integration scenarios.
"""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.config_drift_reconciler import (
    ConfigDriftReconcilerEngine,
    ConfigField,
    DriftAnalysis,
    DriftReport,
    DriftSource,
    ReconciliationAction,
    ReconciliationResult,
    ReconciliationStep,
    _field_risk,
    _infer_drift_source,
    _risk_level_label,
    _FIELD_SPECS,
    _RISK_WEIGHTS,
    _SAFE_ACTIONS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str = "",
    ctype: ComponentType = ComponentType.APP_SERVER,
    *,
    replicas: int = 2,
    max_rps: int = 5000,
    max_connections: int = 1000,
    max_memory_mb: float = 8192,
    max_disk_gb: float = 100,
    timeout_seconds: float = 30.0,
    autoscaling: bool = False,
    autoscaling_min: int = 1,
    autoscaling_max: int = 1,
    failover: bool = False,
    promotion_time: float = 30.0,
    health_check_interval: float = 10.0,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    return Component(
        id=cid,
        name=name or cid,
        type=ctype,
        replicas=replicas,
        capacity=Capacity(
            max_rps=max_rps,
            max_connections=max_connections,
            max_memory_mb=max_memory_mb,
            max_disk_gb=max_disk_gb,
            timeout_seconds=timeout_seconds,
        ),
        autoscaling=AutoScalingConfig(
            enabled=autoscaling,
            min_replicas=autoscaling_min,
            max_replicas=autoscaling_max,
        ),
        failover=FailoverConfig(
            enabled=failover,
            promotion_time_seconds=promotion_time,
            health_check_interval_seconds=health_check_interval,
        ),
        health=health,
    )


def _graph(*components: Component, deps: list[Dependency] | None = None) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for d in deps or []:
        g.add_dependency(d)
    return g


# ---------------------------------------------------------------------------
# DriftSource enum
# ---------------------------------------------------------------------------


class TestDriftSource:
    def test_all_values(self):
        assert DriftSource.MANUAL_CHANGE == "manual_change"
        assert DriftSource.AUTO_SCALING_EVENT == "auto_scaling_event"
        assert DriftSource.FAILOVER_EVENT == "failover_event"
        assert DriftSource.HOTFIX == "hotfix"
        assert DriftSource.CONFIG_MANAGEMENT_FAILURE == "config_management_failure"
        assert DriftSource.OPERATOR_ERROR == "operator_error"
        assert DriftSource.MIGRATION_INCOMPLETE == "migration_incomplete"
        assert DriftSource.ENVIRONMENT_PROMOTION == "environment_promotion"

    def test_member_count(self):
        assert len(DriftSource) == 8

    def test_is_str_enum(self):
        assert isinstance(DriftSource.MANUAL_CHANGE, str)


# ---------------------------------------------------------------------------
# ReconciliationAction enum
# ---------------------------------------------------------------------------


class TestReconciliationAction:
    def test_all_values(self):
        assert ReconciliationAction.APPLY_DESIRED == "apply_desired"
        assert ReconciliationAction.ACCEPT_ACTUAL == "accept_actual"
        assert ReconciliationAction.MERGE == "merge"
        assert ReconciliationAction.ROLLBACK == "rollback"
        assert ReconciliationAction.FLAG_FOR_REVIEW == "flag_for_review"
        assert ReconciliationAction.AUTO_REMEDIATE == "auto_remediate"

    def test_member_count(self):
        assert len(ReconciliationAction) == 6

    def test_is_str_enum(self):
        assert isinstance(ReconciliationAction.APPLY_DESIRED, str)


# ---------------------------------------------------------------------------
# ConfigField model
# ---------------------------------------------------------------------------


class TestConfigField:
    def test_basic_creation(self):
        cf = ConfigField(
            path="replicas",
            desired_value="3",
            actual_value="1",
            drift_source=DriftSource.MANUAL_CHANGE,
            last_changed="2025-01-01",
            risk_level="high",
        )
        assert cf.path == "replicas"
        assert cf.desired_value == "3"
        assert cf.actual_value == "1"
        assert cf.drift_source == DriftSource.MANUAL_CHANGE
        assert cf.last_changed == "2025-01-01"
        assert cf.risk_level == "high"

    def test_serialization_round_trip(self):
        cf = ConfigField(
            path="capacity.max_rps",
            desired_value="10000",
            actual_value="5000",
            drift_source=DriftSource.HOTFIX,
            last_changed="unknown",
            risk_level="medium",
        )
        data = cf.model_dump()
        cf2 = ConfigField(**data)
        assert cf2 == cf


# ---------------------------------------------------------------------------
# ReconciliationStep model
# ---------------------------------------------------------------------------


class TestReconciliationStep:
    def test_basic_creation(self):
        step = ReconciliationStep(
            field_path="replicas",
            action=ReconciliationAction.APPLY_DESIRED,
            rationale="Restore desired replica count.",
            risk="low",
            rollback_safe=True,
        )
        assert step.field_path == "replicas"
        assert step.action == ReconciliationAction.APPLY_DESIRED
        assert step.rollback_safe is True

    def test_flag_for_review_not_safe(self):
        step = ReconciliationStep(
            field_path="failover.enabled",
            action=ReconciliationAction.FLAG_FOR_REVIEW,
            rationale="Needs review.",
            risk="critical",
            rollback_safe=False,
        )
        assert step.rollback_safe is False


# ---------------------------------------------------------------------------
# DriftAnalysis model
# ---------------------------------------------------------------------------


class TestDriftAnalysis:
    def test_defaults(self):
        da = DriftAnalysis(component_id="svc-1", total_fields_checked=10)
        assert da.drifted_fields == []
        assert da.drift_percentage == 0.0
        assert da.risk_score == 0.0
        assert da.recommended_actions == []

    def test_with_fields(self):
        cf = ConfigField(
            path="replicas",
            desired_value="3",
            actual_value="1",
            drift_source=DriftSource.MANUAL_CHANGE,
            last_changed="unknown",
            risk_level="high",
        )
        da = DriftAnalysis(
            component_id="svc-1",
            total_fields_checked=10,
            drifted_fields=[cf],
            drift_percentage=10.0,
            risk_score=15.0,
        )
        assert len(da.drifted_fields) == 1
        assert da.drift_percentage == 10.0


# ---------------------------------------------------------------------------
# ReconciliationResult model
# ---------------------------------------------------------------------------


class TestReconciliationResult:
    def test_defaults(self):
        rr = ReconciliationResult(component_id="x")
        assert rr.steps_applied == 0
        assert rr.steps_failed == 0
        assert rr.success is True

    def test_failure(self):
        rr = ReconciliationResult(
            component_id="x",
            steps_applied=1,
            steps_failed=1,
            fields_reconciled=["a"],
            fields_remaining=["b"],
            success=False,
        )
        assert rr.success is False
        assert rr.steps_failed == 1


# ---------------------------------------------------------------------------
# DriftReport model
# ---------------------------------------------------------------------------


class TestDriftReport:
    def test_defaults(self):
        dr = DriftReport()
        assert dr.total_components == 0
        assert dr.summary == ""

    def test_with_analyses(self):
        da = DriftAnalysis(component_id="a", total_fields_checked=5)
        dr = DriftReport(
            total_components=1,
            analyses=[da],
            summary="OK",
        )
        assert len(dr.analyses) == 1


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_risk_level_label_critical(self):
        assert _risk_level_label(70) == "critical"
        assert _risk_level_label(100) == "critical"

    def test_risk_level_label_high(self):
        assert _risk_level_label(50) == "high"
        assert _risk_level_label(69) == "high"

    def test_risk_level_label_medium(self):
        assert _risk_level_label(30) == "medium"
        assert _risk_level_label(49) == "medium"

    def test_risk_level_label_low(self):
        assert _risk_level_label(0) == "low"
        assert _risk_level_label(29) == "low"

    def test_field_risk_known(self):
        assert _field_risk("replicas") == 15.0
        assert _field_risk("failover.enabled") == 14.0

    def test_field_risk_unknown_defaults(self):
        assert _field_risk("some.unknown.path") == 5.0

    def test_infer_drift_source_replicas_increase(self):
        assert _infer_drift_source("replicas", "2", "4") == DriftSource.AUTO_SCALING_EVENT

    def test_infer_drift_source_replicas_decrease(self):
        assert _infer_drift_source("replicas", "4", "2") == DriftSource.MANUAL_CHANGE

    def test_infer_drift_source_replicas_non_numeric(self):
        assert _infer_drift_source("replicas", "x", "y") == DriftSource.MANUAL_CHANGE

    def test_infer_drift_source_failover(self):
        assert _infer_drift_source("failover.enabled", "True", "False") == DriftSource.FAILOVER_EVENT

    def test_infer_drift_source_autoscaling(self):
        assert _infer_drift_source("autoscaling.min_replicas", "1", "2") == DriftSource.AUTO_SCALING_EVENT

    def test_infer_drift_source_health(self):
        assert _infer_drift_source("health", "healthy", "degraded") == DriftSource.FAILOVER_EVENT

    def test_infer_drift_source_type(self):
        assert _infer_drift_source("type", "app_server", "web_server") == DriftSource.MIGRATION_INCOMPLETE

    def test_infer_drift_source_generic(self):
        assert _infer_drift_source("capacity.max_rps", "5000", "3000") == DriftSource.MANUAL_CHANGE

    def test_field_specs_count(self):
        assert len(_FIELD_SPECS) == 14

    def test_risk_weights_count(self):
        assert len(_RISK_WEIGHTS) == 14

    def test_safe_actions_set(self):
        assert ReconciliationAction.APPLY_DESIRED in _SAFE_ACTIONS
        assert ReconciliationAction.FLAG_FOR_REVIEW not in _SAFE_ACTIONS


# ---------------------------------------------------------------------------
# ConfigDriftReconcilerEngine — detect_field_drift
# ---------------------------------------------------------------------------


class TestDetectFieldDrift:
    def setup_method(self):
        self.engine = ConfigDriftReconcilerEngine()

    def test_no_drift(self):
        c = _comp("a")
        drifts = self.engine.detect_field_drift(c, c)
        assert drifts == []

    def test_replica_drift(self):
        actual = _comp("a", replicas=1)
        desired = _comp("a", replicas=3)
        drifts = self.engine.detect_field_drift(actual, desired)
        paths = [d.path for d in drifts]
        assert "replicas" in paths

    def test_capacity_max_rps_drift(self):
        actual = _comp("a", max_rps=1000)
        desired = _comp("a", max_rps=5000)
        drifts = self.engine.detect_field_drift(actual, desired)
        paths = [d.path for d in drifts]
        assert "capacity.max_rps" in paths

    def test_autoscaling_enabled_drift(self):
        actual = _comp("a", autoscaling=False)
        desired = _comp("a", autoscaling=True)
        drifts = self.engine.detect_field_drift(actual, desired)
        paths = [d.path for d in drifts]
        assert "autoscaling.enabled" in paths

    def test_failover_enabled_drift(self):
        actual = _comp("a", failover=False)
        desired = _comp("a", failover=True)
        drifts = self.engine.detect_field_drift(actual, desired)
        paths = [d.path for d in drifts]
        assert "failover.enabled" in paths

    def test_health_drift(self):
        actual = _comp("a", health=HealthStatus.DEGRADED)
        desired = _comp("a", health=HealthStatus.HEALTHY)
        drifts = self.engine.detect_field_drift(actual, desired)
        paths = [d.path for d in drifts]
        assert "health" in paths

    def test_type_drift(self):
        actual = _comp("a", ctype=ComponentType.WEB_SERVER)
        desired = _comp("a", ctype=ComponentType.APP_SERVER)
        drifts = self.engine.detect_field_drift(actual, desired)
        paths = [d.path for d in drifts]
        assert "type" in paths

    def test_multiple_drifts(self):
        actual = _comp("a", replicas=1, max_rps=100, autoscaling=True)
        desired = _comp("a", replicas=3, max_rps=5000, autoscaling=False)
        drifts = self.engine.detect_field_drift(actual, desired)
        assert len(drifts) >= 3

    def test_drift_source_assigned(self):
        actual = _comp("a", replicas=4)
        desired = _comp("a", replicas=2)
        drifts = self.engine.detect_field_drift(actual, desired)
        rep = [d for d in drifts if d.path == "replicas"][0]
        assert rep.drift_source == DriftSource.AUTO_SCALING_EVENT

    def test_risk_level_assigned(self):
        actual = _comp("a", replicas=1)
        desired = _comp("a", replicas=3)
        drifts = self.engine.detect_field_drift(actual, desired)
        rep = [d for d in drifts if d.path == "replicas"][0]
        assert rep.risk_level in ("low", "medium", "high", "critical")

    def test_max_connections_drift(self):
        actual = _comp("a", max_connections=500)
        desired = _comp("a", max_connections=1000)
        drifts = self.engine.detect_field_drift(actual, desired)
        paths = [d.path for d in drifts]
        assert "capacity.max_connections" in paths

    def test_max_memory_drift(self):
        actual = _comp("a", max_memory_mb=4096)
        desired = _comp("a", max_memory_mb=8192)
        drifts = self.engine.detect_field_drift(actual, desired)
        paths = [d.path for d in drifts]
        assert "capacity.max_memory_mb" in paths

    def test_max_disk_drift(self):
        actual = _comp("a", max_disk_gb=50)
        desired = _comp("a", max_disk_gb=100)
        drifts = self.engine.detect_field_drift(actual, desired)
        paths = [d.path for d in drifts]
        assert "capacity.max_disk_gb" in paths

    def test_timeout_drift(self):
        actual = _comp("a", timeout_seconds=60.0)
        desired = _comp("a", timeout_seconds=30.0)
        drifts = self.engine.detect_field_drift(actual, desired)
        paths = [d.path for d in drifts]
        assert "capacity.timeout_seconds" in paths

    def test_promotion_time_drift(self):
        actual = _comp("a", promotion_time=60.0)
        desired = _comp("a", promotion_time=30.0)
        drifts = self.engine.detect_field_drift(actual, desired)
        paths = [d.path for d in drifts]
        assert "failover.promotion_time_seconds" in paths

    def test_health_check_interval_drift(self):
        actual = _comp("a", health_check_interval=30.0)
        desired = _comp("a", health_check_interval=10.0)
        drifts = self.engine.detect_field_drift(actual, desired)
        paths = [d.path for d in drifts]
        assert "failover.health_check_interval_seconds" in paths

    def test_autoscaling_min_replicas_drift(self):
        actual = _comp("a", autoscaling_min=2)
        desired = _comp("a", autoscaling_min=1)
        drifts = self.engine.detect_field_drift(actual, desired)
        paths = [d.path for d in drifts]
        assert "autoscaling.min_replicas" in paths

    def test_autoscaling_max_replicas_drift(self):
        actual = _comp("a", autoscaling_max=10)
        desired = _comp("a", autoscaling_max=5)
        drifts = self.engine.detect_field_drift(actual, desired)
        paths = [d.path for d in drifts]
        assert "autoscaling.max_replicas" in paths


# ---------------------------------------------------------------------------
# ConfigDriftReconcilerEngine — analyze_drift
# ---------------------------------------------------------------------------


class TestAnalyzeDrift:
    def setup_method(self):
        self.engine = ConfigDriftReconcilerEngine()

    def test_identical_graphs(self):
        c = _comp("a")
        g1 = _graph(c)
        g2 = _graph(c)
        analyses = self.engine.analyze_drift(g1, g2)
        assert len(analyses) == 1
        assert analyses[0].drifted_fields == []
        assert analyses[0].drift_percentage == 0.0

    def test_single_field_drift(self):
        g1 = _graph(_comp("a", replicas=1))
        g2 = _graph(_comp("a", replicas=3))
        analyses = self.engine.analyze_drift(g1, g2)
        assert len(analyses) == 1
        assert len(analyses[0].drifted_fields) >= 1
        assert analyses[0].drift_percentage > 0

    def test_multiple_components(self):
        g1 = _graph(_comp("a"), _comp("b", replicas=1))
        g2 = _graph(_comp("a"), _comp("b", replicas=3))
        analyses = self.engine.analyze_drift(g1, g2)
        assert len(analyses) == 2

    def test_component_in_actual_only(self):
        g1 = _graph(_comp("a"), _comp("extra"))
        g2 = _graph(_comp("a"))
        analyses = self.engine.analyze_drift(g1, g2)
        extra_analysis = [a for a in analyses if a.component_id == "extra"]
        assert len(extra_analysis) == 1
        assert extra_analysis[0].drifted_fields[0].path == "component_exists"
        assert extra_analysis[0].drifted_fields[0].desired_value == "false"

    def test_component_in_desired_only(self):
        g1 = _graph(_comp("a"))
        g2 = _graph(_comp("a"), _comp("missing"))
        analyses = self.engine.analyze_drift(g1, g2)
        missing_analysis = [a for a in analyses if a.component_id == "missing"]
        assert len(missing_analysis) == 1
        assert missing_analysis[0].drifted_fields[0].desired_value == "true"
        assert missing_analysis[0].drifted_fields[0].actual_value == "false"

    def test_recommended_actions_populated(self):
        g1 = _graph(_comp("a", replicas=1))
        g2 = _graph(_comp("a", replicas=3))
        analyses = self.engine.analyze_drift(g1, g2)
        assert len(analyses[0].recommended_actions) > 0

    def test_risk_score_populated(self):
        g1 = _graph(_comp("a", replicas=1, failover=True))
        g2 = _graph(_comp("a", replicas=3, failover=False))
        analyses = self.engine.analyze_drift(g1, g2)
        assert analyses[0].risk_score > 0

    def test_empty_graphs(self):
        g1 = _graph()
        g2 = _graph()
        analyses = self.engine.analyze_drift(g1, g2)
        assert analyses == []

    def test_total_fields_checked(self):
        g1 = _graph(_comp("a"))
        g2 = _graph(_comp("a"))
        analyses = self.engine.analyze_drift(g1, g2)
        assert analyses[0].total_fields_checked == len(_FIELD_SPECS)

    def test_sorted_by_component_id(self):
        g1 = _graph(_comp("z"), _comp("a"), _comp("m"))
        g2 = _graph(_comp("z"), _comp("a"), _comp("m"))
        analyses = self.engine.analyze_drift(g1, g2)
        ids = [a.component_id for a in analyses]
        assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# ConfigDriftReconcilerEngine — recommend_reconciliation
# ---------------------------------------------------------------------------


class TestRecommendReconciliation:
    def setup_method(self):
        self.engine = ConfigDriftReconcilerEngine()

    def test_hotfix_source_accepts_actual(self):
        cf = ConfigField(
            path="capacity.max_rps",
            desired_value="5000",
            actual_value="10000",
            drift_source=DriftSource.HOTFIX,
            last_changed="unknown",
            risk_level="medium",
        )
        da = DriftAnalysis(component_id="a", total_fields_checked=10, drifted_fields=[cf])
        steps = self.engine.recommend_reconciliation(da)
        assert steps[0].action == ReconciliationAction.ACCEPT_ACTUAL

    def test_autoscaling_replicas_accepts_actual(self):
        cf = ConfigField(
            path="replicas",
            desired_value="2",
            actual_value="5",
            drift_source=DriftSource.AUTO_SCALING_EVENT,
            last_changed="unknown",
            risk_level="low",
        )
        da = DriftAnalysis(component_id="a", total_fields_checked=10, drifted_fields=[cf])
        steps = self.engine.recommend_reconciliation(da)
        assert steps[0].action == ReconciliationAction.ACCEPT_ACTUAL

    def test_failover_event_flags_review(self):
        cf = ConfigField(
            path="failover.enabled",
            desired_value="True",
            actual_value="False",
            drift_source=DriftSource.FAILOVER_EVENT,
            last_changed="unknown",
            risk_level="critical",
        )
        da = DriftAnalysis(component_id="a", total_fields_checked=10, drifted_fields=[cf])
        steps = self.engine.recommend_reconciliation(da)
        assert steps[0].action == ReconciliationAction.FLAG_FOR_REVIEW

    def test_operator_error_rollback(self):
        cf = ConfigField(
            path="replicas",
            desired_value="3",
            actual_value="1",
            drift_source=DriftSource.OPERATOR_ERROR,
            last_changed="unknown",
            risk_level="high",
        )
        da = DriftAnalysis(component_id="a", total_fields_checked=10, drifted_fields=[cf])
        steps = self.engine.recommend_reconciliation(da)
        assert steps[0].action == ReconciliationAction.ROLLBACK
        assert steps[0].rollback_safe is True

    def test_config_management_failure_auto_remediate(self):
        cf = ConfigField(
            path="autoscaling.enabled",
            desired_value="True",
            actual_value="False",
            drift_source=DriftSource.CONFIG_MANAGEMENT_FAILURE,
            last_changed="unknown",
            risk_level="high",
        )
        da = DriftAnalysis(component_id="a", total_fields_checked=10, drifted_fields=[cf])
        steps = self.engine.recommend_reconciliation(da)
        assert steps[0].action == ReconciliationAction.AUTO_REMEDIATE

    def test_migration_incomplete_merge(self):
        cf = ConfigField(
            path="type",
            desired_value="app_server",
            actual_value="web_server",
            drift_source=DriftSource.MIGRATION_INCOMPLETE,
            last_changed="unknown",
            risk_level="medium",
        )
        da = DriftAnalysis(component_id="a", total_fields_checked=10, drifted_fields=[cf])
        steps = self.engine.recommend_reconciliation(da)
        assert steps[0].action == ReconciliationAction.MERGE

    def test_environment_promotion_apply_desired(self):
        cf = ConfigField(
            path="capacity.max_rps",
            desired_value="10000",
            actual_value="5000",
            drift_source=DriftSource.ENVIRONMENT_PROMOTION,
            last_changed="unknown",
            risk_level="medium",
        )
        da = DriftAnalysis(component_id="a", total_fields_checked=10, drifted_fields=[cf])
        steps = self.engine.recommend_reconciliation(da)
        assert steps[0].action == ReconciliationAction.APPLY_DESIRED

    def test_default_manual_change_apply_desired(self):
        cf = ConfigField(
            path="capacity.max_connections",
            desired_value="1000",
            actual_value="500",
            drift_source=DriftSource.MANUAL_CHANGE,
            last_changed="unknown",
            risk_level="medium",
        )
        da = DriftAnalysis(component_id="a", total_fields_checked=10, drifted_fields=[cf])
        steps = self.engine.recommend_reconciliation(da)
        assert steps[0].action == ReconciliationAction.APPLY_DESIRED

    def test_critical_risk_flags_review(self):
        cf = ConfigField(
            path="replicas",
            desired_value="3",
            actual_value="1",
            drift_source=DriftSource.MANUAL_CHANGE,
            last_changed="unknown",
            risk_level="critical",
        )
        da = DriftAnalysis(component_id="a", total_fields_checked=10, drifted_fields=[cf])
        steps = self.engine.recommend_reconciliation(da)
        assert steps[0].action == ReconciliationAction.FLAG_FOR_REVIEW

    def test_empty_drift_returns_no_steps(self):
        da = DriftAnalysis(component_id="a", total_fields_checked=10)
        steps = self.engine.recommend_reconciliation(da)
        assert steps == []

    def test_multiple_fields_multiple_steps(self):
        cf1 = ConfigField(
            path="replicas", desired_value="3", actual_value="5",
            drift_source=DriftSource.AUTO_SCALING_EVENT,
            last_changed="unknown", risk_level="low",
        )
        cf2 = ConfigField(
            path="failover.enabled", desired_value="True", actual_value="False",
            drift_source=DriftSource.FAILOVER_EVENT,
            last_changed="unknown", risk_level="critical",
        )
        da = DriftAnalysis(
            component_id="a", total_fields_checked=10,
            drifted_fields=[cf1, cf2],
        )
        steps = self.engine.recommend_reconciliation(da)
        assert len(steps) == 2

    def test_autoscaling_non_replicas_not_accept_actual(self):
        cf = ConfigField(
            path="autoscaling.min_replicas",
            desired_value="1",
            actual_value="3",
            drift_source=DriftSource.AUTO_SCALING_EVENT,
            last_changed="unknown",
            risk_level="medium",
        )
        da = DriftAnalysis(component_id="a", total_fields_checked=10, drifted_fields=[cf])
        steps = self.engine.recommend_reconciliation(da)
        # AUTO_SCALING_EVENT on non-replicas path falls through to default
        assert steps[0].action != ReconciliationAction.FLAG_FOR_REVIEW


# ---------------------------------------------------------------------------
# ConfigDriftReconcilerEngine — calculate_drift_risk
# ---------------------------------------------------------------------------


class TestCalculateDriftRisk:
    def setup_method(self):
        self.engine = ConfigDriftReconcilerEngine()

    def test_no_drifts_zero_risk(self):
        assert self.engine.calculate_drift_risk([]) == 0.0

    def test_single_replicas_drift(self):
        cf = ConfigField(
            path="replicas", desired_value="3", actual_value="1",
            drift_source=DriftSource.MANUAL_CHANGE,
            last_changed="unknown", risk_level="high",
        )
        risk = self.engine.calculate_drift_risk([cf])
        assert risk == 15.0  # replicas weight

    def test_operator_error_amplification(self):
        cf = ConfigField(
            path="replicas", desired_value="3", actual_value="1",
            drift_source=DriftSource.OPERATOR_ERROR,
            last_changed="unknown", risk_level="high",
        )
        risk = self.engine.calculate_drift_risk([cf])
        assert risk == 15.0 * 1.5

    def test_config_management_failure_amplification(self):
        cf = ConfigField(
            path="replicas", desired_value="3", actual_value="1",
            drift_source=DriftSource.CONFIG_MANAGEMENT_FAILURE,
            last_changed="unknown", risk_level="high",
        )
        risk = self.engine.calculate_drift_risk([cf])
        assert risk == 15.0 * 1.5

    def test_hotfix_amplification(self):
        cf = ConfigField(
            path="replicas", desired_value="3", actual_value="1",
            drift_source=DriftSource.HOTFIX,
            last_changed="unknown", risk_level="high",
        )
        risk = self.engine.calculate_drift_risk([cf])
        assert risk == 15.0 * 1.2

    def test_multiple_fields_add_up(self):
        cf1 = ConfigField(
            path="replicas", desired_value="3", actual_value="1",
            drift_source=DriftSource.MANUAL_CHANGE,
            last_changed="unknown", risk_level="high",
        )
        cf2 = ConfigField(
            path="failover.enabled", desired_value="True", actual_value="False",
            drift_source=DriftSource.MANUAL_CHANGE,
            last_changed="unknown", risk_level="high",
        )
        risk = self.engine.calculate_drift_risk([cf1, cf2])
        assert risk == 15.0 + 14.0

    def test_capped_at_100(self):
        fields = []
        for path, weight in _RISK_WEIGHTS.items():
            fields.append(ConfigField(
                path=path, desired_value="a", actual_value="b",
                drift_source=DriftSource.OPERATOR_ERROR,
                last_changed="unknown", risk_level="high",
            ))
        risk = self.engine.calculate_drift_risk(fields)
        assert risk == 100.0

    def test_unknown_path_uses_default_weight(self):
        cf = ConfigField(
            path="unknown.field", desired_value="a", actual_value="b",
            drift_source=DriftSource.MANUAL_CHANGE,
            last_changed="unknown", risk_level="low",
        )
        risk = self.engine.calculate_drift_risk([cf])
        assert risk == 5.0

    def test_normal_source_no_amplification(self):
        cf = ConfigField(
            path="capacity.max_rps", desired_value="5000", actual_value="3000",
            drift_source=DriftSource.ENVIRONMENT_PROMOTION,
            last_changed="unknown", risk_level="medium",
        )
        risk = self.engine.calculate_drift_risk([cf])
        assert risk == 10.0  # max_rps weight, no multiplier


# ---------------------------------------------------------------------------
# ConfigDriftReconcilerEngine — simulate_reconciliation
# ---------------------------------------------------------------------------


class TestSimulateReconciliation:
    def setup_method(self):
        self.engine = ConfigDriftReconcilerEngine()

    def test_full_reconciliation_success(self):
        # Use a drift that produces APPLY_DESIRED (not FLAG_FOR_REVIEW)
        actual = _graph(_comp("a", max_connections=500))
        desired = _graph(_comp("a", max_connections=1000))
        analyses = self.engine.analyze_drift(actual, desired)
        actions = analyses[0].recommended_actions
        # Verify at least one action is not FLAG_FOR_REVIEW
        assert any(a.action != ReconciliationAction.FLAG_FOR_REVIEW for a in actions)
        result = self.engine.simulate_reconciliation(actual, desired, actions)
        assert result.steps_applied > 0
        assert result.risk_after <= result.risk_before

    def test_no_actions_everything_remaining(self):
        actual = _graph(_comp("a", replicas=1))
        desired = _graph(_comp("a", replicas=3))
        result = self.engine.simulate_reconciliation(actual, desired, [])
        assert result.steps_applied == 0
        assert len(result.fields_remaining) > 0

    def test_flag_for_review_stays_remaining(self):
        actual = _graph(_comp("a", failover=True))
        desired = _graph(_comp("a", failover=False))
        action = ReconciliationStep(
            field_path="failover.enabled",
            action=ReconciliationAction.FLAG_FOR_REVIEW,
            rationale="Review needed.",
            risk="high",
            rollback_safe=False,
        )
        result = self.engine.simulate_reconciliation(actual, desired, [action])
        assert "failover.enabled" in result.fields_remaining

    def test_unsafe_rollback_fails(self):
        actual = _graph(_comp("a", replicas=1))
        desired = _graph(_comp("a", replicas=3))
        action = ReconciliationStep(
            field_path="replicas",
            action=ReconciliationAction.ROLLBACK,
            rationale="Rollback.",
            risk="high",
            rollback_safe=False,
        )
        result = self.engine.simulate_reconciliation(actual, desired, [action])
        assert result.steps_failed >= 1
        assert result.success is False

    def test_safe_rollback_succeeds(self):
        actual = _graph(_comp("a", replicas=1))
        desired = _graph(_comp("a", replicas=3))
        action = ReconciliationStep(
            field_path="replicas",
            action=ReconciliationAction.ROLLBACK,
            rationale="Rollback.",
            risk="low",
            rollback_safe=True,
        )
        result = self.engine.simulate_reconciliation(actual, desired, [action])
        assert "replicas" in result.fields_reconciled

    def test_identical_graphs_nothing_to_do(self):
        g = _graph(_comp("a"))
        result = self.engine.simulate_reconciliation(g, g, [])
        assert result.steps_applied == 0
        assert result.fields_remaining == []
        assert result.success is True

    def test_risk_after_less_or_equal(self):
        actual = _graph(_comp("a", replicas=1, failover=True))
        desired = _graph(_comp("a", replicas=3, failover=False))
        analyses = self.engine.analyze_drift(actual, desired)
        actions = analyses[0].recommended_actions
        result = self.engine.simulate_reconciliation(actual, desired, actions)
        assert result.risk_after <= result.risk_before

    def test_component_id_set(self):
        actual = _graph(_comp("svc-1", replicas=1))
        desired = _graph(_comp("svc-1", replicas=3))
        result = self.engine.simulate_reconciliation(actual, desired, [])
        assert result.component_id == "svc-1"

    def test_empty_graphs(self):
        g1 = _graph()
        g2 = _graph()
        result = self.engine.simulate_reconciliation(g1, g2, [])
        assert result.component_id == ""
        assert result.success is True


# ---------------------------------------------------------------------------
# ConfigDriftReconcilerEngine — generate_drift_report
# ---------------------------------------------------------------------------


class TestGenerateDriftReport:
    def setup_method(self):
        self.engine = ConfigDriftReconcilerEngine()

    def test_no_analyses(self):
        report = self.engine.generate_drift_report([])
        assert report.total_components == 0
        assert report.summary == "No configuration drift detected."

    def test_no_drifts(self):
        da = DriftAnalysis(component_id="a", total_fields_checked=10)
        report = self.engine.generate_drift_report([da])
        assert report.components_with_drift == 0
        assert report.total_drifted_fields == 0
        assert "No configuration drift" in report.summary

    def test_with_drifts(self):
        cf = ConfigField(
            path="replicas", desired_value="3", actual_value="1",
            drift_source=DriftSource.MANUAL_CHANGE,
            last_changed="unknown", risk_level="high",
        )
        da = DriftAnalysis(
            component_id="a", total_fields_checked=10,
            drifted_fields=[cf], drift_percentage=10.0, risk_score=15.0,
        )
        report = self.engine.generate_drift_report([da])
        assert report.components_with_drift == 1
        assert report.total_drifted_fields == 1
        assert "1 drifted field(s)" in report.summary

    def test_multiple_components(self):
        cf1 = ConfigField(
            path="replicas", desired_value="3", actual_value="1",
            drift_source=DriftSource.MANUAL_CHANGE,
            last_changed="unknown", risk_level="high",
        )
        cf2 = ConfigField(
            path="failover.enabled", desired_value="True", actual_value="False",
            drift_source=DriftSource.MANUAL_CHANGE,
            last_changed="unknown", risk_level="high",
        )
        da1 = DriftAnalysis(
            component_id="a", total_fields_checked=10,
            drifted_fields=[cf1], risk_score=15.0,
        )
        da2 = DriftAnalysis(
            component_id="b", total_fields_checked=10,
            drifted_fields=[cf2], risk_score=14.0,
        )
        report = self.engine.generate_drift_report([da1, da2])
        assert report.total_components == 2
        assert report.components_with_drift == 2
        assert report.total_drifted_fields == 2

    def test_reconciliation_order_by_risk_desc(self):
        da1 = DriftAnalysis(
            component_id="low",
            total_fields_checked=10,
            drifted_fields=[ConfigField(
                path="replicas", desired_value="3", actual_value="2",
                drift_source=DriftSource.MANUAL_CHANGE,
                last_changed="unknown", risk_level="low",
            )],
            risk_score=5.0,
        )
        da2 = DriftAnalysis(
            component_id="high",
            total_fields_checked=10,
            drifted_fields=[ConfigField(
                path="replicas", desired_value="3", actual_value="1",
                drift_source=DriftSource.MANUAL_CHANGE,
                last_changed="unknown", risk_level="high",
            )],
            risk_score=15.0,
        )
        report = self.engine.generate_drift_report([da1, da2])
        assert report.reconciliation_order == ["high", "low"]

    def test_overall_risk_score(self):
        cf = ConfigField(
            path="replicas", desired_value="3", actual_value="1",
            drift_source=DriftSource.MANUAL_CHANGE,
            last_changed="unknown", risk_level="high",
        )
        da = DriftAnalysis(
            component_id="a", total_fields_checked=10,
            drifted_fields=[cf], risk_score=15.0,
        )
        report = self.engine.generate_drift_report([da])
        assert report.overall_risk_score == 15.0

    def test_analyses_preserved(self):
        da = DriftAnalysis(component_id="z", total_fields_checked=5)
        report = self.engine.generate_drift_report([da])
        assert report.analyses == [da]


# ---------------------------------------------------------------------------
# ConfigDriftReconcilerEngine — find_safe_reconciliation_order
# ---------------------------------------------------------------------------


class TestFindSafeReconciliationOrder:
    def setup_method(self):
        self.engine = ConfigDriftReconcilerEngine()

    def test_no_drift_empty(self):
        g = _graph(_comp("a"))
        da = DriftAnalysis(component_id="a", total_fields_checked=10)
        order = self.engine.find_safe_reconciliation_order(g, [da])
        assert order == []

    def test_single_drifted_component(self):
        g = _graph(_comp("a"))
        cf = ConfigField(
            path="replicas", desired_value="3", actual_value="1",
            drift_source=DriftSource.MANUAL_CHANGE,
            last_changed="unknown", risk_level="high",
        )
        da = DriftAnalysis(
            component_id="a", total_fields_checked=10,
            drifted_fields=[cf], risk_score=15.0,
        )
        order = self.engine.find_safe_reconciliation_order(g, [da])
        assert order == ["a"]

    def test_fewer_dependents_first(self):
        """Components with fewer dependents should be reconciled first.

        In 'upstream -> leaf', upstream depends on leaf, meaning leaf has
        1 dependent (upstream) while upstream has 0 dependents.  So upstream
        is reconciled first.
        """
        leaf = _comp("leaf")
        upstream = _comp("upstream")
        dep = Dependency(source_id="upstream", target_id="leaf")
        g = _graph(leaf, upstream, deps=[dep])

        cf = ConfigField(
            path="replicas", desired_value="3", actual_value="1",
            drift_source=DriftSource.MANUAL_CHANGE,
            last_changed="unknown", risk_level="high",
        )
        da_leaf = DriftAnalysis(
            component_id="leaf", total_fields_checked=10,
            drifted_fields=[cf], risk_score=15.0,
        )
        da_upstream = DriftAnalysis(
            component_id="upstream", total_fields_checked=10,
            drifted_fields=[cf], risk_score=15.0,
        )
        order = self.engine.find_safe_reconciliation_order(g, [da_leaf, da_upstream])
        # upstream has 0 dependents, leaf has 1 — upstream comes first
        assert order.index("upstream") < order.index("leaf")

    def test_same_depth_low_risk_first(self):
        """Among components with same depth, lower risk comes first."""
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b)

        cf_low = ConfigField(
            path="replicas", desired_value="3", actual_value="2",
            drift_source=DriftSource.MANUAL_CHANGE,
            last_changed="unknown", risk_level="low",
        )
        cf_high = ConfigField(
            path="replicas", desired_value="3", actual_value="1",
            drift_source=DriftSource.MANUAL_CHANGE,
            last_changed="unknown", risk_level="high",
        )
        da_low = DriftAnalysis(
            component_id="a", total_fields_checked=10,
            drifted_fields=[cf_low], risk_score=5.0,
        )
        da_high = DriftAnalysis(
            component_id="b", total_fields_checked=10,
            drifted_fields=[cf_high], risk_score=15.0,
        )
        order = self.engine.find_safe_reconciliation_order(g, [da_low, da_high])
        assert order.index("a") < order.index("b")

    def test_missing_component_in_graph(self):
        """Component that is in analyses but not in the graph."""
        g = _graph(_comp("a"))
        cf = ConfigField(
            path="replicas", desired_value="3", actual_value="1",
            drift_source=DriftSource.MANUAL_CHANGE,
            last_changed="unknown", risk_level="high",
        )
        da = DriftAnalysis(
            component_id="ghost", total_fields_checked=10,
            drifted_fields=[cf], risk_score=10.0,
        )
        order = self.engine.find_safe_reconciliation_order(g, [da])
        assert order == ["ghost"]

    def test_complex_dependency_chain(self):
        """A -> B -> C: C has most dependents, should be last."""
        a = _comp("a")
        b = _comp("b")
        c = _comp("c")
        deps = [
            Dependency(source_id="a", target_id="b"),
            Dependency(source_id="b", target_id="c"),
        ]
        g = _graph(a, b, c, deps=deps)

        cf = ConfigField(
            path="replicas", desired_value="3", actual_value="1",
            drift_source=DriftSource.MANUAL_CHANGE,
            last_changed="unknown", risk_level="high",
        )
        analyses = [
            DriftAnalysis(component_id="a", total_fields_checked=10,
                          drifted_fields=[cf], risk_score=10.0),
            DriftAnalysis(component_id="b", total_fields_checked=10,
                          drifted_fields=[cf], risk_score=10.0),
            DriftAnalysis(component_id="c", total_fields_checked=10,
                          drifted_fields=[cf], risk_score=10.0),
        ]
        order = self.engine.find_safe_reconciliation_order(g, analyses)
        # a has 0 dependents, b has 1 (a), c has 1 (b)
        assert order[0] == "a"


# ---------------------------------------------------------------------------
# _pick_action internal — additional edge cases
# ---------------------------------------------------------------------------


class TestPickAction:
    def setup_method(self):
        self.engine = ConfigDriftReconcilerEngine()

    def test_hotfix_rollback_safe(self):
        action, _, _, rollback = self.engine._pick_action(
            ConfigField(
                path="x", desired_value="a", actual_value="b",
                drift_source=DriftSource.HOTFIX,
                last_changed="unknown", risk_level="low",
            )
        )
        assert action == ReconciliationAction.ACCEPT_ACTUAL
        assert rollback is True

    def test_operator_error_rationale_contains_path(self):
        _, rationale, _, _ = self.engine._pick_action(
            ConfigField(
                path="replicas", desired_value="3", actual_value="1",
                drift_source=DriftSource.OPERATOR_ERROR,
                last_changed="unknown", risk_level="high",
            )
        )
        assert "replicas" in rationale

    def test_environment_promotion_low_risk(self):
        _, _, risk, _ = self.engine._pick_action(
            ConfigField(
                path="capacity.max_rps", desired_value="10000", actual_value="5000",
                drift_source=DriftSource.ENVIRONMENT_PROMOTION,
                last_changed="unknown", risk_level="medium",
            )
        )
        assert risk == "low"

    def test_merge_not_rollback_safe(self):
        _, _, _, rollback = self.engine._pick_action(
            ConfigField(
                path="type", desired_value="app_server", actual_value="web_server",
                drift_source=DriftSource.MIGRATION_INCOMPLETE,
                last_changed="unknown", risk_level="medium",
            )
        )
        assert rollback is False

    def test_flag_review_not_rollback_safe(self):
        _, _, _, rollback = self.engine._pick_action(
            ConfigField(
                path="failover.enabled", desired_value="True", actual_value="False",
                drift_source=DriftSource.FAILOVER_EVENT,
                last_changed="unknown", risk_level="critical",
            )
        )
        assert rollback is False


# ---------------------------------------------------------------------------
# _missing_component_analysis
# ---------------------------------------------------------------------------


class TestMissingComponentAnalysis:
    def setup_method(self):
        self.engine = ConfigDriftReconcilerEngine()

    def test_actual_missing(self):
        da = self.engine._missing_component_analysis("x", None, _comp("x"))
        assert da.drifted_fields[0].desired_value == "true"
        assert da.drifted_fields[0].actual_value == "false"
        assert da.drifted_fields[0].drift_source == DriftSource.CONFIG_MANAGEMENT_FAILURE
        assert da.drifted_fields[0].risk_level == "critical"

    def test_desired_missing(self):
        da = self.engine._missing_component_analysis("x", _comp("x"), None)
        assert da.drifted_fields[0].desired_value == "false"
        assert da.drifted_fields[0].actual_value == "true"
        assert da.drifted_fields[0].drift_source == DriftSource.MANUAL_CHANGE
        assert da.drifted_fields[0].risk_level == "high"

    def test_actual_missing_higher_risk(self):
        da_actual = self.engine._missing_component_analysis("x", None, _comp("x"))
        da_desired = self.engine._missing_component_analysis("x", _comp("x"), None)
        assert da_actual.risk_score > da_desired.risk_score

    def test_recommended_actions_populated(self):
        da = self.engine._missing_component_analysis("x", None, _comp("x"))
        assert len(da.recommended_actions) == 1

    def test_total_fields_one(self):
        da = self.engine._missing_component_analysis("x", None, _comp("x"))
        assert da.total_fields_checked == 1
        assert da.drift_percentage == 100.0


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestIntegration:
    def setup_method(self):
        self.engine = ConfigDriftReconcilerEngine()

    def test_end_to_end_no_drift(self):
        c = _comp("web", replicas=3, failover=True)
        g = _graph(c)
        analyses = self.engine.analyze_drift(g, g)
        report = self.engine.generate_drift_report(analyses)
        assert report.components_with_drift == 0
        assert report.overall_risk_score == 0.0

    def test_end_to_end_with_drift(self):
        actual = _graph(
            _comp("web", replicas=1, max_rps=1000),
            _comp("db", failover=True),
        )
        desired = _graph(
            _comp("web", replicas=3, max_rps=5000),
            _comp("db", failover=False),
        )
        analyses = self.engine.analyze_drift(actual, desired)
        report = self.engine.generate_drift_report(analyses)
        assert report.components_with_drift == 2
        assert report.overall_risk_score > 0

    def test_end_to_end_reconciliation(self):
        actual = _graph(_comp("app", replicas=1))
        desired = _graph(_comp("app", replicas=3))
        analyses = self.engine.analyze_drift(actual, desired)
        actions = analyses[0].recommended_actions
        result = self.engine.simulate_reconciliation(actual, desired, actions)
        assert result.risk_after <= result.risk_before

    def test_safe_order_then_reconcile(self):
        """root -> mid -> leaf: root has 0 dependents so it is reconciled first."""
        leaf = _comp("leaf", replicas=1)
        mid = _comp("mid", replicas=1)
        root = _comp("root", replicas=1)
        deps = [
            Dependency(source_id="root", target_id="mid"),
            Dependency(source_id="mid", target_id="leaf"),
        ]
        actual = _graph(leaf, mid, root, deps=deps)

        desired_leaf = _comp("leaf", replicas=3)
        desired_mid = _comp("mid", replicas=3)
        desired_root = _comp("root", replicas=3)
        desired = _graph(desired_leaf, desired_mid, desired_root, deps=deps)

        analyses = self.engine.analyze_drift(actual, desired)
        order = self.engine.find_safe_reconciliation_order(actual, analyses)
        assert len(order) == 3
        # root has 0 dependents, mid has 1 (root), leaf has 1 (mid)
        assert order[0] == "root"

    def test_report_summary_contains_count(self):
        actual = _graph(_comp("a", replicas=1))
        desired = _graph(_comp("a", replicas=3))
        analyses = self.engine.analyze_drift(actual, desired)
        report = self.engine.generate_drift_report(analyses)
        assert "drifted field(s)" in report.summary

    def test_report_reconciliation_order_populated(self):
        actual = _graph(_comp("a", replicas=1), _comp("b", max_rps=100))
        desired = _graph(_comp("a", replicas=3), _comp("b", max_rps=5000))
        analyses = self.engine.analyze_drift(actual, desired)
        report = self.engine.generate_drift_report(analyses)
        assert len(report.reconciliation_order) == 2

    def test_large_graph(self):
        """10 components, various drifts."""
        actual_comps = [_comp(f"svc-{i}", replicas=i + 1) for i in range(10)]
        desired_comps = [_comp(f"svc-{i}", replicas=3) for i in range(10)]
        actual = _graph(*actual_comps)
        desired = _graph(*desired_comps)
        analyses = self.engine.analyze_drift(actual, desired)
        report = self.engine.generate_drift_report(analyses)
        assert report.total_components == 10

    def test_mixed_missing_and_drifted(self):
        actual = _graph(_comp("a", replicas=1), _comp("extra"))
        desired = _graph(_comp("a", replicas=3), _comp("needed"))
        analyses = self.engine.analyze_drift(actual, desired)
        ids = {a.component_id for a in analyses}
        assert "a" in ids
        assert "extra" in ids
        assert "needed" in ids
        report = self.engine.generate_drift_report(analyses)
        assert report.components_with_drift >= 3

    def test_simulate_with_partial_actions(self):
        actual = _graph(_comp("a", replicas=1, max_rps=100))
        desired = _graph(_comp("a", replicas=3, max_rps=5000))
        analyses = self.engine.analyze_drift(actual, desired)
        # Only provide action for replicas
        partial = [s for s in analyses[0].recommended_actions if s.field_path == "replicas"]
        result = self.engine.simulate_reconciliation(actual, desired, partial)
        assert result.steps_applied >= 0
        assert len(result.fields_remaining) > 0

    def test_full_pipeline_with_dependencies(self):
        """Full pipeline: analyze -> report -> order -> simulate."""
        web = _comp("web", replicas=1)
        api = _comp("api", replicas=1, max_rps=100)
        db = _comp("db", replicas=1, failover=True)
        deps = [
            Dependency(source_id="web", target_id="api"),
            Dependency(source_id="api", target_id="db"),
        ]
        actual = _graph(web, api, db, deps=deps)

        desired_web = _comp("web", replicas=3)
        desired_api = _comp("api", replicas=2, max_rps=5000)
        desired_db = _comp("db", replicas=2, failover=False)
        desired = _graph(desired_web, desired_api, desired_db, deps=deps)

        # 1. Analyze
        analyses = self.engine.analyze_drift(actual, desired)
        assert len(analyses) == 3

        # 2. Report
        report = self.engine.generate_drift_report(analyses)
        assert report.components_with_drift == 3
        assert report.overall_risk_score > 0

        # 3. Safe order
        order = self.engine.find_safe_reconciliation_order(actual, analyses)
        assert len(order) == 3
        # web -> api -> db: web has 0 dependents, so it is first
        assert order[0] == "web"

        # 4. Simulate reconciliation for each component
        for cid in order:
            comp_analysis = [a for a in analyses if a.component_id == cid][0]
            result = self.engine.simulate_reconciliation(
                actual, desired, comp_analysis.recommended_actions
            )
            assert result.risk_after <= result.risk_before


# ---------------------------------------------------------------------------
# Edge cases and model validation
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def setup_method(self):
        self.engine = ConfigDriftReconcilerEngine()

    def test_component_with_all_defaults(self):
        c = Component(
            id="default", name="default",
            type=ComponentType.APP_SERVER,
        )
        drifts = self.engine.detect_field_drift(c, c)
        assert drifts == []

    def test_database_type(self):
        actual = _comp("db", ctype=ComponentType.DATABASE)
        desired = _comp("db", ctype=ComponentType.CACHE)
        drifts = self.engine.detect_field_drift(actual, desired)
        paths = [d.path for d in drifts]
        assert "type" in paths

    def test_reconciliation_result_serialization(self):
        rr = ReconciliationResult(
            component_id="x",
            steps_applied=2,
            fields_reconciled=["a", "b"],
        )
        data = rr.model_dump()
        rr2 = ReconciliationResult(**data)
        assert rr2.steps_applied == 2

    def test_drift_report_serialization(self):
        report = DriftReport(total_components=5, summary="Test")
        data = report.model_dump()
        report2 = DriftReport(**data)
        assert report2.total_components == 5

    def test_config_field_all_sources(self):
        for source in DriftSource:
            cf = ConfigField(
                path="replicas", desired_value="3", actual_value="1",
                drift_source=source, last_changed="now",
                risk_level="medium",
            )
            assert cf.drift_source == source

    def test_reconciliation_step_all_actions(self):
        for action in ReconciliationAction:
            step = ReconciliationStep(
                field_path="test",
                action=action,
                rationale="test",
                risk="low",
                rollback_safe=True,
            )
            assert step.action == action

    def test_analyze_drift_graph_with_deps_only(self):
        """Dependencies exist but components are identical."""
        a = _comp("a")
        b = _comp("b")
        dep = Dependency(source_id="a", target_id="b")
        g1 = _graph(a, b, deps=[dep])
        g2 = _graph(a, b, deps=[dep])
        analyses = self.engine.analyze_drift(g1, g2)
        assert all(len(a.drifted_fields) == 0 for a in analyses)

    def test_drift_percentage_calculation(self):
        actual = _graph(_comp("a", replicas=1, max_rps=100, autoscaling=True))
        desired = _graph(_comp("a", replicas=3, max_rps=5000, autoscaling=False))
        analyses = self.engine.analyze_drift(actual, desired)
        pct = analyses[0].drift_percentage
        assert 0 < pct <= 100

    def test_health_status_drift_down(self):
        actual = _comp("a", health=HealthStatus.DOWN)
        desired = _comp("a", health=HealthStatus.HEALTHY)
        drifts = self.engine.detect_field_drift(actual, desired)
        health_drifts = [d for d in drifts if d.path == "health"]
        assert len(health_drifts) == 1
        assert health_drifts[0].actual_value == "down"

    def test_overloaded_health_drift(self):
        actual = _comp("a", health=HealthStatus.OVERLOADED)
        desired = _comp("a", health=HealthStatus.HEALTHY)
        drifts = self.engine.detect_field_drift(actual, desired)
        health_drifts = [d for d in drifts if d.path == "health"]
        assert len(health_drifts) == 1
