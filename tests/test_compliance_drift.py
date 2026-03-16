"""Tests for compliance_drift module — 100% coverage target."""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph
from faultray.simulator.compliance_drift import (
    ComplianceBaseline,
    ComplianceDriftEngine,
    ComplianceDriftItem,
    ComplianceDriftReport,
    ComplianceFramework,
    ComplianceTrajectory,
    DriftSeverity,
    DriftType,
    RemediationPlan,
    RemediationPriority,
    _CONTROL_IDS,
    _FRAMEWORK_SEVERITY,
    _REGULATORY_RISK,
    _REMEDIATION_STEPS,
    _SEVERITY_EFFORT,
    _SEVERITY_PRIORITY,
    _SEVERITY_WEIGHT,
    _drift_item_id,
    _resolve_control_id,
    _resolve_severity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(cid="c1", ctype=ComponentType.APP_SERVER):
    return Component(id=cid, name=cid, type=ctype)


def _graph(*comps):
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _secure_comp(cid="sec1"):
    """Component with all security features enabled."""
    c = Component(id=cid, name=cid, type=ComponentType.APP_SERVER)
    c.security.encryption_at_rest = True
    c.security.encryption_in_transit = True
    c.security.log_enabled = True
    c.security.auth_required = True
    c.security.backup_enabled = True
    c.security.network_segmented = True
    c.security.waf_protected = True
    c.security.rate_limiting = True
    c.security.ids_monitored = True
    return c


def _baseline(
    fw=ComplianceFramework.SOC2,
    sid="snap-1",
    ts="2025-01-01T00:00:00Z",
    assessed=10,
    passing=8,
    failing=2,
    score=80.0,
):
    return ComplianceBaseline(
        snapshot_id=sid,
        framework=fw,
        timestamp=ts,
        controls_assessed=assessed,
        controls_passing=passing,
        controls_failing=failing,
        score=score,
    )


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestEnums:
    def test_compliance_framework_values(self):
        assert ComplianceFramework.SOC2.value == "soc2"
        assert ComplianceFramework.HIPAA.value == "hipaa"
        assert ComplianceFramework.PCI_DSS.value == "pci_dss"
        assert ComplianceFramework.GDPR.value == "gdpr"
        assert ComplianceFramework.ISO_27001.value == "iso_27001"
        assert ComplianceFramework.NIST_CSF.value == "nist_csf"
        assert ComplianceFramework.FedRAMP.value == "fedramp"
        assert ComplianceFramework.CIS_BENCHMARK.value == "cis_benchmark"

    def test_drift_type_values(self):
        assert DriftType.NEW_VIOLATION.value == "new_violation"
        assert DriftType.REGRESSION.value == "regression"
        assert DriftType.CONFIGURATION_CHANGE.value == "configuration_change"
        assert DriftType.PERMISSION_ESCALATION.value == "permission_escalation"
        assert DriftType.ENCRYPTION_REMOVED.value == "encryption_removed"
        assert DriftType.LOGGING_DISABLED.value == "logging_disabled"
        assert DriftType.BACKUP_POLICY_CHANGED.value == "backup_policy_changed"
        assert DriftType.NETWORK_EXPOSURE.value == "network_exposure"

    def test_drift_severity_values(self):
        assert DriftSeverity.CRITICAL.value == "critical"
        assert DriftSeverity.HIGH.value == "high"
        assert DriftSeverity.MEDIUM.value == "medium"
        assert DriftSeverity.LOW.value == "low"
        assert DriftSeverity.INFO.value == "info"

    def test_remediation_priority_values(self):
        assert RemediationPriority.IMMEDIATE.value == "immediate"
        assert RemediationPriority.URGENT.value == "urgent"
        assert RemediationPriority.STANDARD.value == "standard"
        assert RemediationPriority.DEFERRED.value == "deferred"


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestModels:
    def test_compliance_baseline_construction(self):
        bl = _baseline()
        assert bl.snapshot_id == "snap-1"
        assert bl.framework == ComplianceFramework.SOC2
        assert bl.controls_assessed == 10
        assert bl.controls_passing == 8
        assert bl.controls_failing == 2
        assert bl.score == 80.0

    def test_compliance_baseline_defaults(self):
        bl = ComplianceBaseline(
            snapshot_id="x", framework=ComplianceFramework.GDPR, timestamp="t"
        )
        assert bl.controls_assessed == 0
        assert bl.controls_passing == 0
        assert bl.controls_failing == 0
        assert bl.score == 0.0

    def test_compliance_drift_item_construction(self):
        item = ComplianceDriftItem(
            component_id="c1",
            drift_type=DriftType.ENCRYPTION_REMOVED,
            severity=DriftSeverity.CRITICAL,
            framework=ComplianceFramework.PCI_DSS,
            control_id="Req-3.4",
            baseline_state="enc=true",
            current_state="enc=false",
            description="Encryption removed",
            remediation="Re-enable",
        )
        assert item.component_id == "c1"
        assert item.drift_type == DriftType.ENCRYPTION_REMOVED
        assert item.severity == DriftSeverity.CRITICAL

    def test_compliance_trajectory_defaults(self):
        traj = ComplianceTrajectory(framework=ComplianceFramework.HIPAA)
        assert traj.scores == []
        assert traj.timestamps == []
        assert traj.trend == "stable"
        assert traj.projected_score == 0.0

    def test_remediation_plan_construction(self):
        plan = RemediationPlan(
            drift_item_id="abc123",
            priority=RemediationPriority.IMMEDIATE,
            estimated_effort_hours=8.0,
            regulatory_risk="High risk",
            remediation_steps=["step1", "step2"],
        )
        assert plan.drift_item_id == "abc123"
        assert plan.priority == RemediationPriority.IMMEDIATE
        assert len(plan.remediation_steps) == 2

    def test_remediation_plan_defaults(self):
        plan = RemediationPlan(drift_item_id="x", priority=RemediationPriority.DEFERRED)
        assert plan.estimated_effort_hours == 0.0
        assert plan.regulatory_risk == ""
        assert plan.remediation_steps == []

    def test_compliance_drift_report_defaults(self):
        report = ComplianceDriftReport()
        assert report.drifts == []
        assert report.trajectory == []
        assert report.remediation_plans == []
        assert report.overall_drift_score == 0.0
        assert report.frameworks_affected == []
        assert report.total_controls_drifted == 0
        assert report.recommendations == []


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    def test_drift_item_id_deterministic(self):
        item = ComplianceDriftItem(
            component_id="c1",
            drift_type=DriftType.ENCRYPTION_REMOVED,
            severity=DriftSeverity.CRITICAL,
            framework=ComplianceFramework.SOC2,
            control_id="CC6.1",
            baseline_state="x",
            current_state="y",
            description="d",
            remediation="r",
        )
        id1 = _drift_item_id(item)
        id2 = _drift_item_id(item)
        assert id1 == id2
        assert len(id1) == 12

    def test_drift_item_id_different_for_different_items(self):
        item1 = ComplianceDriftItem(
            component_id="c1",
            drift_type=DriftType.ENCRYPTION_REMOVED,
            severity=DriftSeverity.CRITICAL,
            framework=ComplianceFramework.SOC2,
            control_id="CC6.1",
            baseline_state="x",
            current_state="y",
            description="d",
            remediation="r",
        )
        item2 = ComplianceDriftItem(
            component_id="c2",
            drift_type=DriftType.LOGGING_DISABLED,
            severity=DriftSeverity.HIGH,
            framework=ComplianceFramework.HIPAA,
            control_id="164.312(b)",
            baseline_state="x",
            current_state="y",
            description="d",
            remediation="r",
        )
        assert _drift_item_id(item1) != _drift_item_id(item2)

    def test_resolve_severity_known(self):
        sev = _resolve_severity(ComplianceFramework.PCI_DSS, DriftType.ENCRYPTION_REMOVED)
        assert sev == DriftSeverity.CRITICAL

    def test_resolve_severity_default(self):
        sev = _resolve_severity(ComplianceFramework.CIS_BENCHMARK, DriftType.CONFIGURATION_CHANGE)
        assert sev == DriftSeverity.LOW

    def test_resolve_control_id_known(self):
        cid = _resolve_control_id(ComplianceFramework.SOC2, DriftType.ENCRYPTION_REMOVED)
        assert cid == "CC6.1"

    def test_resolve_control_id_hipaa(self):
        cid = _resolve_control_id(ComplianceFramework.HIPAA, DriftType.LOGGING_DISABLED)
        assert cid == "164.312(b)"

    def test_resolve_control_id_pci(self):
        cid = _resolve_control_id(ComplianceFramework.PCI_DSS, DriftType.BACKUP_POLICY_CHANGED)
        assert cid == "Req-9.5"


# ---------------------------------------------------------------------------
# Mapping table tests
# ---------------------------------------------------------------------------


class TestMappingTables:
    def test_all_frameworks_have_severity_map(self):
        for fw in ComplianceFramework:
            assert fw in _FRAMEWORK_SEVERITY

    def test_all_frameworks_have_regulatory_risk(self):
        for fw in ComplianceFramework:
            assert fw in _REGULATORY_RISK

    def test_all_frameworks_have_control_ids(self):
        for fw in ComplianceFramework:
            assert fw in _CONTROL_IDS

    def test_all_severities_have_weight(self):
        for sev in DriftSeverity:
            assert sev in _SEVERITY_WEIGHT

    def test_all_severities_have_effort(self):
        for sev in DriftSeverity:
            assert sev in _SEVERITY_EFFORT

    def test_all_severities_have_priority(self):
        for sev in DriftSeverity:
            assert sev in _SEVERITY_PRIORITY

    def test_all_drift_types_have_remediation_steps(self):
        for dt in DriftType:
            assert dt in _REMEDIATION_STEPS

    def test_severity_weight_ordering(self):
        assert _SEVERITY_WEIGHT[DriftSeverity.CRITICAL] > _SEVERITY_WEIGHT[DriftSeverity.HIGH]
        assert _SEVERITY_WEIGHT[DriftSeverity.HIGH] > _SEVERITY_WEIGHT[DriftSeverity.MEDIUM]
        assert _SEVERITY_WEIGHT[DriftSeverity.MEDIUM] > _SEVERITY_WEIGHT[DriftSeverity.LOW]
        assert _SEVERITY_WEIGHT[DriftSeverity.LOW] > _SEVERITY_WEIGHT[DriftSeverity.INFO]

    def test_severity_effort_ordering(self):
        assert _SEVERITY_EFFORT[DriftSeverity.CRITICAL] > _SEVERITY_EFFORT[DriftSeverity.HIGH]
        assert _SEVERITY_EFFORT[DriftSeverity.HIGH] > _SEVERITY_EFFORT[DriftSeverity.MEDIUM]

    def test_framework_severity_covers_all_drift_types(self):
        for fw in ComplianceFramework:
            for dt in DriftType:
                assert dt in _FRAMEWORK_SEVERITY[fw]

    def test_control_ids_covers_all_drift_types(self):
        for fw in ComplianceFramework:
            for dt in DriftType:
                assert dt in _CONTROL_IDS[fw]


# ---------------------------------------------------------------------------
# detect_drift tests
# ---------------------------------------------------------------------------


class TestDetectDrift:
    def test_no_drift_when_state_matches_baseline(self):
        comp = _secure_comp("s1")
        graph = _graph(comp)
        baselines = [_baseline(fw=ComplianceFramework.SOC2)]
        state = {
            "s1": {
                "encryption_at_rest": True,
                "encryption_in_transit": True,
                "logging_enabled": True,
                "auth_required": True,
                "backup_enabled": True,
                "network_segmented": True,
                "waf_protected": True,
                "rate_limiting": True,
                "ids_monitored": True,
            }
        }
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, state)
        assert report.total_controls_drifted == 0
        assert report.overall_drift_score == 0.0

    def test_encryption_at_rest_drift(self):
        comp = _secure_comp("s1")
        graph = _graph(comp)
        baselines = [_baseline(fw=ComplianceFramework.SOC2)]
        state = {"s1": {"encryption_at_rest": False}}
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, state)
        assert report.total_controls_drifted >= 1
        enc_drifts = [d for d in report.drifts if d.drift_type == DriftType.ENCRYPTION_REMOVED]
        assert len(enc_drifts) >= 1

    def test_encryption_in_transit_drift(self):
        comp = _secure_comp("s1")
        graph = _graph(comp)
        baselines = [_baseline(fw=ComplianceFramework.SOC2)]
        state = {"s1": {"encryption_in_transit": False}}
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, state)
        enc_drifts = [
            d for d in report.drifts
            if d.drift_type == DriftType.ENCRYPTION_REMOVED
            and "transit" in d.description
        ]
        assert len(enc_drifts) >= 1

    def test_logging_disabled_drift(self):
        comp = _secure_comp("s1")
        graph = _graph(comp)
        baselines = [_baseline(fw=ComplianceFramework.HIPAA)]
        state = {"s1": {"logging_enabled": False}}
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, state)
        log_drifts = [d for d in report.drifts if d.drift_type == DriftType.LOGGING_DISABLED]
        assert len(log_drifts) >= 1

    def test_auth_removed_drift(self):
        comp = _secure_comp("s1")
        graph = _graph(comp)
        baselines = [_baseline(fw=ComplianceFramework.PCI_DSS)]
        state = {"s1": {"auth_required": False}}
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, state)
        auth_drifts = [d for d in report.drifts if d.drift_type == DriftType.PERMISSION_ESCALATION]
        assert len(auth_drifts) >= 1

    def test_backup_disabled_drift(self):
        comp = _secure_comp("s1")
        graph = _graph(comp)
        baselines = [_baseline(fw=ComplianceFramework.GDPR)]
        state = {"s1": {"backup_enabled": False}}
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, state)
        backup_drifts = [d for d in report.drifts if d.drift_type == DriftType.BACKUP_POLICY_CHANGED]
        assert len(backup_drifts) >= 1

    def test_network_segmentation_removed_drift(self):
        comp = _secure_comp("s1")
        graph = _graph(comp)
        baselines = [_baseline(fw=ComplianceFramework.NIST_CSF)]
        state = {"s1": {"network_segmented": False}}
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, state)
        net_drifts = [d for d in report.drifts if d.drift_type == DriftType.NETWORK_EXPOSURE]
        assert len(net_drifts) >= 1

    def test_waf_removed_drift(self):
        comp = _secure_comp("s1")
        graph = _graph(comp)
        baselines = [_baseline(fw=ComplianceFramework.FedRAMP)]
        state = {"s1": {"waf_protected": False}}
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, state)
        waf_drifts = [
            d for d in report.drifts
            if d.drift_type == DriftType.NETWORK_EXPOSURE and "WAF" in d.description
        ]
        assert len(waf_drifts) >= 1

    def test_rate_limiting_removed_drift(self):
        comp = _secure_comp("s1")
        graph = _graph(comp)
        baselines = [_baseline(fw=ComplianceFramework.CIS_BENCHMARK)]
        state = {"s1": {"rate_limiting": False}}
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, state)
        rate_drifts = [d for d in report.drifts if d.drift_type == DriftType.CONFIGURATION_CHANGE]
        assert len(rate_drifts) >= 1

    def test_ids_monitoring_removed_drift(self):
        comp = _secure_comp("s1")
        graph = _graph(comp)
        baselines = [_baseline(fw=ComplianceFramework.ISO_27001)]
        state = {"s1": {"ids_monitored": False}}
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, state)
        ids_drifts = [
            d for d in report.drifts
            if "IDS" in d.description
        ]
        assert len(ids_drifts) >= 1

    def test_multiple_drifts_single_component(self):
        comp = _secure_comp("s1")
        graph = _graph(comp)
        baselines = [_baseline(fw=ComplianceFramework.SOC2)]
        state = {
            "s1": {
                "encryption_at_rest": False,
                "logging_enabled": False,
                "auth_required": False,
            }
        }
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, state)
        assert report.total_controls_drifted >= 3

    def test_multiple_components_drift(self):
        c1 = _secure_comp("s1")
        c2 = _secure_comp("s2")
        graph = _graph(c1, c2)
        baselines = [_baseline(fw=ComplianceFramework.SOC2)]
        state = {
            "s1": {"encryption_at_rest": False},
            "s2": {"logging_enabled": False},
        }
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, state)
        comp_ids = {d.component_id for d in report.drifts}
        assert "s1" in comp_ids
        assert "s2" in comp_ids

    def test_multiple_frameworks_drift(self):
        comp = _secure_comp("s1")
        graph = _graph(comp)
        baselines = [
            _baseline(fw=ComplianceFramework.SOC2),
            _baseline(fw=ComplianceFramework.HIPAA, sid="snap-2"),
        ]
        state = {"s1": {"encryption_at_rest": False}}
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, state)
        fws = {d.framework for d in report.drifts}
        assert ComplianceFramework.SOC2 in fws
        assert ComplianceFramework.HIPAA in fws
        assert len(report.frameworks_affected) == 2

    def test_no_state_for_component_no_drift(self):
        comp = _secure_comp("s1")
        graph = _graph(comp)
        baselines = [_baseline(fw=ComplianceFramework.SOC2)]
        state = {}  # No current state — defaults to baseline
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, state)
        assert report.total_controls_drifted == 0

    def test_report_has_trajectory(self):
        comp = _comp("c1")
        graph = _graph(comp)
        baselines = [
            _baseline(fw=ComplianceFramework.SOC2, ts="2025-01-01", score=80.0, sid="s1"),
            _baseline(fw=ComplianceFramework.SOC2, ts="2025-02-01", score=85.0, sid="s2"),
        ]
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, {})
        assert len(report.trajectory) >= 1

    def test_report_has_remediation_plans_when_drifts(self):
        comp = _secure_comp("s1")
        graph = _graph(comp)
        baselines = [_baseline(fw=ComplianceFramework.SOC2)]
        state = {"s1": {"encryption_at_rest": False}}
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, state)
        assert len(report.remediation_plans) >= 1

    def test_report_has_recommendations(self):
        comp = _secure_comp("s1")
        graph = _graph(comp)
        baselines = [_baseline(fw=ComplianceFramework.SOC2)]
        state = {"s1": {"encryption_at_rest": False}}
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, state)
        assert len(report.recommendations) >= 1

    def test_empty_graph_no_drift(self):
        graph = InfraGraph()
        baselines = [_baseline(fw=ComplianceFramework.SOC2)]
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, {})
        assert report.total_controls_drifted == 0

    def test_empty_baselines_no_drift(self):
        comp = _secure_comp("s1")
        graph = _graph(comp)
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, [], {"s1": {"encryption_at_rest": False}})
        assert report.total_controls_drifted == 0

    def test_non_secure_component_no_drift_when_unchanged(self):
        comp = _comp("c1")  # all security features off by default
        graph = _graph(comp)
        baselines = [_baseline(fw=ComplianceFramework.SOC2)]
        state = {"c1": {"encryption_at_rest": False}}
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, state)
        # Component had encryption off in baseline, still off — no drift
        assert report.total_controls_drifted == 0


# ---------------------------------------------------------------------------
# compare_baselines tests
# ---------------------------------------------------------------------------


class TestCompareBaselines:
    def test_no_change(self):
        old = _baseline(score=80.0, failing=2, passing=8)
        new = _baseline(score=80.0, failing=2, passing=8, sid="s2", ts="2025-02-01")
        engine = ComplianceDriftEngine()
        items = engine.compare_baselines(old, new)
        assert len(items) == 0

    def test_more_failing_controls(self):
        old = _baseline(failing=2, passing=8)
        new = _baseline(failing=5, passing=5, sid="s2", ts="2025-02-01")
        engine = ComplianceDriftEngine()
        items = engine.compare_baselines(old, new)
        regression_items = [i for i in items if "additional control" in i.description]
        assert len(regression_items) >= 1

    def test_score_drop_medium(self):
        old = _baseline(score=80.0)
        new = _baseline(score=75.0, sid="s2", ts="2025-02-01")
        engine = ComplianceDriftEngine()
        items = engine.compare_baselines(old, new)
        score_items = [i for i in items if "score dropped" in i.description]
        assert len(score_items) >= 1
        assert score_items[0].severity == DriftSeverity.MEDIUM

    def test_score_drop_high(self):
        old = _baseline(score=90.0)
        new = _baseline(score=78.0, sid="s2", ts="2025-02-01")
        engine = ComplianceDriftEngine()
        items = engine.compare_baselines(old, new)
        score_items = [i for i in items if "score dropped" in i.description]
        assert len(score_items) >= 1
        assert score_items[0].severity == DriftSeverity.HIGH

    def test_score_drop_critical(self):
        old = _baseline(score=90.0)
        new = _baseline(score=65.0, sid="s2", ts="2025-02-01")
        engine = ComplianceDriftEngine()
        items = engine.compare_baselines(old, new)
        score_items = [i for i in items if "score dropped" in i.description]
        assert len(score_items) >= 1
        assert score_items[0].severity == DriftSeverity.CRITICAL

    def test_fewer_passing_controls(self):
        old = _baseline(passing=10)
        new = _baseline(passing=7, sid="s2", ts="2025-02-01")
        engine = ComplianceDriftEngine()
        items = engine.compare_baselines(old, new)
        new_violation_items = [i for i in items if i.drift_type == DriftType.NEW_VIOLATION]
        assert len(new_violation_items) >= 1

    def test_different_frameworks_returns_empty(self):
        old = _baseline(fw=ComplianceFramework.SOC2)
        new = _baseline(fw=ComplianceFramework.HIPAA, sid="s2")
        engine = ComplianceDriftEngine()
        items = engine.compare_baselines(old, new)
        assert len(items) == 0

    def test_improvement_no_drift(self):
        old = _baseline(score=70.0, failing=5, passing=5)
        new = _baseline(score=90.0, failing=1, passing=9, sid="s2", ts="2025-02-01")
        engine = ComplianceDriftEngine()
        items = engine.compare_baselines(old, new)
        assert len(items) == 0


# ---------------------------------------------------------------------------
# compute_trajectory tests
# ---------------------------------------------------------------------------


class TestComputeTrajectory:
    def test_single_baseline(self):
        baselines = [_baseline(score=80.0)]
        engine = ComplianceDriftEngine()
        trajs = engine.compute_trajectory(baselines)
        assert len(trajs) == 1
        assert trajs[0].framework == ComplianceFramework.SOC2
        assert trajs[0].scores == [80.0]
        assert trajs[0].trend == "stable"
        assert trajs[0].projected_score == 80.0

    def test_improving_trajectory(self):
        baselines = [
            _baseline(score=60.0, ts="2025-01-01", sid="s1"),
            _baseline(score=70.0, ts="2025-02-01", sid="s2"),
            _baseline(score=80.0, ts="2025-03-01", sid="s3"),
            _baseline(score=90.0, ts="2025-04-01", sid="s4"),
        ]
        engine = ComplianceDriftEngine()
        trajs = engine.compute_trajectory(baselines)
        assert len(trajs) == 1
        assert trajs[0].trend == "improving"
        assert trajs[0].projected_score == 100.0  # 90 + (90-80) capped at 100

    def test_declining_trajectory(self):
        baselines = [
            _baseline(score=90.0, ts="2025-01-01", sid="s1"),
            _baseline(score=80.0, ts="2025-02-01", sid="s2"),
            _baseline(score=70.0, ts="2025-03-01", sid="s3"),
            _baseline(score=60.0, ts="2025-04-01", sid="s4"),
        ]
        engine = ComplianceDriftEngine()
        trajs = engine.compute_trajectory(baselines)
        assert trajs[0].trend == "declining"
        assert trajs[0].projected_score == 50.0

    def test_stable_trajectory(self):
        baselines = [
            _baseline(score=80.0, ts="2025-01-01", sid="s1"),
            _baseline(score=80.5, ts="2025-02-01", sid="s2"),
            _baseline(score=80.0, ts="2025-03-01", sid="s3"),
            _baseline(score=80.5, ts="2025-04-01", sid="s4"),
        ]
        engine = ComplianceDriftEngine()
        trajs = engine.compute_trajectory(baselines)
        assert trajs[0].trend == "stable"

    def test_multiple_frameworks(self):
        baselines = [
            _baseline(fw=ComplianceFramework.SOC2, score=80.0, sid="s1"),
            _baseline(fw=ComplianceFramework.HIPAA, score=75.0, sid="s2"),
        ]
        engine = ComplianceDriftEngine()
        trajs = engine.compute_trajectory(baselines)
        assert len(trajs) == 2
        fws = {t.framework for t in trajs}
        assert ComplianceFramework.SOC2 in fws
        assert ComplianceFramework.HIPAA in fws

    def test_empty_baselines(self):
        engine = ComplianceDriftEngine()
        trajs = engine.compute_trajectory([])
        assert trajs == []

    def test_projection_capped_at_zero(self):
        baselines = [
            _baseline(score=10.0, ts="2025-01-01", sid="s1"),
            _baseline(score=5.0, ts="2025-02-01", sid="s2"),
        ]
        engine = ComplianceDriftEngine()
        trajs = engine.compute_trajectory(baselines)
        assert trajs[0].projected_score == 0.0  # 5 + (5-10) = 0

    def test_projection_capped_at_100(self):
        baselines = [
            _baseline(score=90.0, ts="2025-01-01", sid="s1"),
            _baseline(score=98.0, ts="2025-02-01", sid="s2"),
        ]
        engine = ComplianceDriftEngine()
        trajs = engine.compute_trajectory(baselines)
        assert trajs[0].projected_score == 100.0  # 98 + (98-90) = 106 -> capped 100

    def test_two_datapoints_trend(self):
        baselines = [
            _baseline(score=50.0, ts="2025-01-01", sid="s1"),
            _baseline(score=60.0, ts="2025-02-01", sid="s2"),
        ]
        engine = ComplianceDriftEngine()
        trajs = engine.compute_trajectory(baselines)
        assert trajs[0].trend == "improving"

    def test_timestamps_sorted(self):
        baselines = [
            _baseline(score=80.0, ts="2025-03-01", sid="s3"),
            _baseline(score=70.0, ts="2025-01-01", sid="s1"),
            _baseline(score=75.0, ts="2025-02-01", sid="s2"),
        ]
        engine = ComplianceDriftEngine()
        trajs = engine.compute_trajectory(baselines)
        assert trajs[0].timestamps == ["2025-01-01", "2025-02-01", "2025-03-01"]
        assert trajs[0].scores == [70.0, 75.0, 80.0]


# ---------------------------------------------------------------------------
# generate_remediation_plan tests
# ---------------------------------------------------------------------------


class TestGenerateRemediationPlan:
    def test_critical_encryption_plan(self):
        item = ComplianceDriftItem(
            component_id="c1",
            drift_type=DriftType.ENCRYPTION_REMOVED,
            severity=DriftSeverity.CRITICAL,
            framework=ComplianceFramework.PCI_DSS,
            control_id="Req-3.4",
            baseline_state="enc=true",
            current_state="enc=false",
            description="Encryption removed",
            remediation="Re-enable",
        )
        engine = ComplianceDriftEngine()
        plan = engine.generate_remediation_plan(item)
        assert plan.priority == RemediationPriority.IMMEDIATE
        assert plan.estimated_effort_hours == 8.0
        assert "CRITICAL" in plan.regulatory_risk
        assert len(plan.remediation_steps) >= 3

    def test_high_logging_plan(self):
        item = ComplianceDriftItem(
            component_id="c1",
            drift_type=DriftType.LOGGING_DISABLED,
            severity=DriftSeverity.HIGH,
            framework=ComplianceFramework.SOC2,
            control_id="CC7.2",
            baseline_state="log=true",
            current_state="log=false",
            description="Logging disabled",
            remediation="Re-enable",
        )
        engine = ComplianceDriftEngine()
        plan = engine.generate_remediation_plan(item)
        assert plan.priority == RemediationPriority.URGENT
        assert plan.estimated_effort_hours == 4.0

    def test_medium_config_plan(self):
        item = ComplianceDriftItem(
            component_id="c1",
            drift_type=DriftType.CONFIGURATION_CHANGE,
            severity=DriftSeverity.MEDIUM,
            framework=ComplianceFramework.ISO_27001,
            control_id="A.14.2.2",
            baseline_state="a=1",
            current_state="a=2",
            description="Config changed",
            remediation="Revert",
        )
        engine = ComplianceDriftEngine()
        plan = engine.generate_remediation_plan(item)
        assert plan.priority == RemediationPriority.STANDARD
        assert plan.estimated_effort_hours == 2.0

    def test_low_severity_plan(self):
        item = ComplianceDriftItem(
            component_id="c1",
            drift_type=DriftType.CONFIGURATION_CHANGE,
            severity=DriftSeverity.LOW,
            framework=ComplianceFramework.CIS_BENCHMARK,
            control_id="CIS-5.1",
            baseline_state="x",
            current_state="y",
            description="Minor change",
            remediation="Review",
        )
        engine = ComplianceDriftEngine()
        plan = engine.generate_remediation_plan(item)
        assert plan.priority == RemediationPriority.DEFERRED
        assert plan.estimated_effort_hours == 1.0

    def test_info_severity_plan(self):
        item = ComplianceDriftItem(
            component_id="c1",
            drift_type=DriftType.CONFIGURATION_CHANGE,
            severity=DriftSeverity.INFO,
            framework=ComplianceFramework.CIS_BENCHMARK,
            control_id="CIS-5.1",
            baseline_state="x",
            current_state="y",
            description="Informational",
            remediation="Note",
        )
        engine = ComplianceDriftEngine()
        plan = engine.generate_remediation_plan(item)
        assert plan.priority == RemediationPriority.DEFERRED
        assert plan.estimated_effort_hours == 0.5

    def test_all_drift_types_produce_steps(self):
        engine = ComplianceDriftEngine()
        for dt in DriftType:
            item = ComplianceDriftItem(
                component_id="c1",
                drift_type=dt,
                severity=DriftSeverity.MEDIUM,
                framework=ComplianceFramework.SOC2,
                control_id="test",
                baseline_state="a",
                current_state="b",
                description="test",
                remediation="test",
            )
            plan = engine.generate_remediation_plan(item)
            assert len(plan.remediation_steps) >= 3


# ---------------------------------------------------------------------------
# assess_regulatory_risk tests
# ---------------------------------------------------------------------------


class TestAssessRegulatoryRisk:
    def test_critical_prefix(self):
        item = ComplianceDriftItem(
            component_id="c1",
            drift_type=DriftType.ENCRYPTION_REMOVED,
            severity=DriftSeverity.CRITICAL,
            framework=ComplianceFramework.HIPAA,
            control_id="x",
            baseline_state="a",
            current_state="b",
            description="d",
            remediation="r",
        )
        engine = ComplianceDriftEngine()
        risk = engine.assess_regulatory_risk(item)
        assert risk.startswith("CRITICAL:")
        assert "HIPAA" in risk

    def test_high_prefix(self):
        item = ComplianceDriftItem(
            component_id="c1",
            drift_type=DriftType.LOGGING_DISABLED,
            severity=DriftSeverity.HIGH,
            framework=ComplianceFramework.PCI_DSS,
            control_id="x",
            baseline_state="a",
            current_state="b",
            description="d",
            remediation="r",
        )
        engine = ComplianceDriftEngine()
        risk = engine.assess_regulatory_risk(item)
        assert risk.startswith("HIGH:")
        assert "PCI" in risk

    def test_medium_no_prefix(self):
        item = ComplianceDriftItem(
            component_id="c1",
            drift_type=DriftType.CONFIGURATION_CHANGE,
            severity=DriftSeverity.MEDIUM,
            framework=ComplianceFramework.GDPR,
            control_id="x",
            baseline_state="a",
            current_state="b",
            description="d",
            remediation="r",
        )
        engine = ComplianceDriftEngine()
        risk = engine.assess_regulatory_risk(item)
        assert not risk.startswith("CRITICAL:")
        assert not risk.startswith("HIGH:")
        assert "GDPR" in risk

    def test_all_frameworks_have_risk(self):
        engine = ComplianceDriftEngine()
        for fw in ComplianceFramework:
            item = ComplianceDriftItem(
                component_id="c1",
                drift_type=DriftType.NEW_VIOLATION,
                severity=DriftSeverity.MEDIUM,
                framework=fw,
                control_id="x",
                baseline_state="a",
                current_state="b",
                description="d",
                remediation="r",
            )
            risk = engine.assess_regulatory_risk(item)
            assert len(risk) > 0


# ---------------------------------------------------------------------------
# prioritize_remediations tests
# ---------------------------------------------------------------------------


class TestPrioritizeRemediations:
    def test_empty_list(self):
        engine = ComplianceDriftEngine()
        plans = engine.prioritize_remediations([])
        assert plans == []

    def test_sorted_by_priority(self):
        items = [
            ComplianceDriftItem(
                component_id="c1",
                drift_type=DriftType.CONFIGURATION_CHANGE,
                severity=DriftSeverity.LOW,
                framework=ComplianceFramework.SOC2,
                control_id="x",
                baseline_state="a",
                current_state="b",
                description="low",
                remediation="r",
            ),
            ComplianceDriftItem(
                component_id="c2",
                drift_type=DriftType.ENCRYPTION_REMOVED,
                severity=DriftSeverity.CRITICAL,
                framework=ComplianceFramework.SOC2,
                control_id="y",
                baseline_state="a",
                current_state="b",
                description="critical",
                remediation="r",
            ),
            ComplianceDriftItem(
                component_id="c3",
                drift_type=DriftType.LOGGING_DISABLED,
                severity=DriftSeverity.HIGH,
                framework=ComplianceFramework.SOC2,
                control_id="z",
                baseline_state="a",
                current_state="b",
                description="high",
                remediation="r",
            ),
        ]
        engine = ComplianceDriftEngine()
        plans = engine.prioritize_remediations(items)
        assert plans[0].priority == RemediationPriority.IMMEDIATE
        assert plans[1].priority == RemediationPriority.URGENT
        assert plans[2].priority == RemediationPriority.DEFERRED

    def test_all_plans_have_steps(self):
        items = [
            ComplianceDriftItem(
                component_id="c1",
                drift_type=dt,
                severity=DriftSeverity.MEDIUM,
                framework=ComplianceFramework.SOC2,
                control_id="x",
                baseline_state="a",
                current_state="b",
                description="d",
                remediation="r",
            )
            for dt in [DriftType.ENCRYPTION_REMOVED, DriftType.LOGGING_DISABLED]
        ]
        engine = ComplianceDriftEngine()
        plans = engine.prioritize_remediations(items)
        for plan in plans:
            assert len(plan.remediation_steps) >= 3


# ---------------------------------------------------------------------------
# Overall drift score tests
# ---------------------------------------------------------------------------


class TestOverallDriftScore:
    def test_zero_drifts_zero_score(self):
        engine = ComplianceDriftEngine()
        score = engine._compute_overall_drift_score([])
        assert score == 0.0

    def test_single_critical_drift(self):
        drifts = [
            ComplianceDriftItem(
                component_id="c1",
                drift_type=DriftType.ENCRYPTION_REMOVED,
                severity=DriftSeverity.CRITICAL,
                framework=ComplianceFramework.SOC2,
                control_id="x",
                baseline_state="a",
                current_state="b",
                description="d",
                remediation="r",
            ),
        ]
        engine = ComplianceDriftEngine()
        score = engine._compute_overall_drift_score(drifts)
        assert score == 10.0

    def test_score_capped_at_100(self):
        drifts = [
            ComplianceDriftItem(
                component_id=f"c{i}",
                drift_type=DriftType.ENCRYPTION_REMOVED,
                severity=DriftSeverity.CRITICAL,
                framework=ComplianceFramework.SOC2,
                control_id="x",
                baseline_state="a",
                current_state="b",
                description="d",
                remediation="r",
            )
            for i in range(20)
        ]
        engine = ComplianceDriftEngine()
        score = engine._compute_overall_drift_score(drifts)
        assert score == 100.0

    def test_info_severity_zero_weight(self):
        drifts = [
            ComplianceDriftItem(
                component_id="c1",
                drift_type=DriftType.CONFIGURATION_CHANGE,
                severity=DriftSeverity.INFO,
                framework=ComplianceFramework.SOC2,
                control_id="x",
                baseline_state="a",
                current_state="b",
                description="d",
                remediation="r",
            ),
        ]
        engine = ComplianceDriftEngine()
        score = engine._compute_overall_drift_score(drifts)
        assert score == 0.0


# ---------------------------------------------------------------------------
# Trend computation tests
# ---------------------------------------------------------------------------


class TestTrendComputation:
    def test_empty_scores(self):
        engine = ComplianceDriftEngine()
        assert engine._compute_trend([]) == "stable"

    def test_single_score(self):
        engine = ComplianceDriftEngine()
        assert engine._compute_trend([80.0]) == "stable"

    def test_improving(self):
        engine = ComplianceDriftEngine()
        assert engine._compute_trend([50.0, 60.0, 70.0, 80.0]) == "improving"

    def test_declining(self):
        engine = ComplianceDriftEngine()
        assert engine._compute_trend([80.0, 70.0, 60.0, 50.0]) == "declining"

    def test_stable_flat(self):
        engine = ComplianceDriftEngine()
        assert engine._compute_trend([80.0, 80.0, 80.0, 80.0]) == "stable"


# ---------------------------------------------------------------------------
# Projection tests
# ---------------------------------------------------------------------------


class TestProjection:
    def test_empty_scores(self):
        engine = ComplianceDriftEngine()
        assert engine._project_score([]) == 0.0

    def test_single_score(self):
        engine = ComplianceDriftEngine()
        assert engine._project_score([75.0]) == 75.0

    def test_upward_projection(self):
        engine = ComplianceDriftEngine()
        assert engine._project_score([70.0, 80.0]) == 90.0

    def test_downward_projection(self):
        engine = ComplianceDriftEngine()
        assert engine._project_score([80.0, 70.0]) == 60.0

    def test_projection_floor_zero(self):
        engine = ComplianceDriftEngine()
        assert engine._project_score([20.0, 5.0]) == 0.0

    def test_projection_cap_100(self):
        engine = ComplianceDriftEngine()
        assert engine._project_score([80.0, 95.0]) == 100.0


# ---------------------------------------------------------------------------
# Recommendations tests
# ---------------------------------------------------------------------------


class TestRecommendations:
    def test_no_drifts_gives_clean_rec(self):
        engine = ComplianceDriftEngine()
        recs = engine._generate_recommendations([], [])
        assert len(recs) == 1
        assert "No compliance drift" in recs[0]

    def test_critical_drift_urgent_rec(self):
        drifts = [
            ComplianceDriftItem(
                component_id="c1",
                drift_type=DriftType.ENCRYPTION_REMOVED,
                severity=DriftSeverity.CRITICAL,
                framework=ComplianceFramework.SOC2,
                control_id="x",
                baseline_state="a",
                current_state="b",
                description="d",
                remediation="r",
            ),
        ]
        engine = ComplianceDriftEngine()
        recs = engine._generate_recommendations(drifts, [])
        urgent = [r for r in recs if "URGENT" in r]
        assert len(urgent) >= 1

    def test_high_drift_rec(self):
        drifts = [
            ComplianceDriftItem(
                component_id="c1",
                drift_type=DriftType.LOGGING_DISABLED,
                severity=DriftSeverity.HIGH,
                framework=ComplianceFramework.SOC2,
                control_id="x",
                baseline_state="a",
                current_state="b",
                description="d",
                remediation="r",
            ),
        ]
        engine = ComplianceDriftEngine()
        recs = engine._generate_recommendations(drifts, [])
        assert any("48 hours" in r for r in recs)

    def test_encryption_recommendation(self):
        drifts = [
            ComplianceDriftItem(
                component_id="c1",
                drift_type=DriftType.ENCRYPTION_REMOVED,
                severity=DriftSeverity.MEDIUM,
                framework=ComplianceFramework.SOC2,
                control_id="x",
                baseline_state="a",
                current_state="b",
                description="d",
                remediation="r",
            ),
        ]
        engine = ComplianceDriftEngine()
        recs = engine._generate_recommendations(drifts, [])
        assert any("encryption" in r.lower() for r in recs)

    def test_logging_recommendation(self):
        drifts = [
            ComplianceDriftItem(
                component_id="c1",
                drift_type=DriftType.LOGGING_DISABLED,
                severity=DriftSeverity.MEDIUM,
                framework=ComplianceFramework.SOC2,
                control_id="x",
                baseline_state="a",
                current_state="b",
                description="d",
                remediation="r",
            ),
        ]
        engine = ComplianceDriftEngine()
        recs = engine._generate_recommendations(drifts, [])
        assert any("logging" in r.lower() for r in recs)

    def test_network_recommendation(self):
        drifts = [
            ComplianceDriftItem(
                component_id="c1",
                drift_type=DriftType.NETWORK_EXPOSURE,
                severity=DriftSeverity.MEDIUM,
                framework=ComplianceFramework.SOC2,
                control_id="x",
                baseline_state="a",
                current_state="b",
                description="d",
                remediation="r",
            ),
        ]
        engine = ComplianceDriftEngine()
        recs = engine._generate_recommendations(drifts, [])
        assert any("network" in r.lower() for r in recs)

    def test_declining_trajectory_recommendation(self):
        drifts: list[ComplianceDriftItem] = []
        trajs = [
            ComplianceTrajectory(
                framework=ComplianceFramework.SOC2,
                scores=[90.0, 80.0, 70.0, 60.0],
                timestamps=["t1", "t2", "t3", "t4"],
                trend="declining",
                projected_score=50.0,
            )
        ]
        engine = ComplianceDriftEngine()
        recs = engine._generate_recommendations(drifts, trajs)
        assert any("declining" in r for r in recs)

    def test_multi_framework_recommendation(self):
        drifts = [
            ComplianceDriftItem(
                component_id="c1",
                drift_type=DriftType.ENCRYPTION_REMOVED,
                severity=DriftSeverity.MEDIUM,
                framework=fw,
                control_id="x",
                baseline_state="a",
                current_state="b",
                description="d",
                remediation="r",
            )
            for fw in [ComplianceFramework.SOC2, ComplianceFramework.HIPAA, ComplianceFramework.PCI_DSS]
        ]
        engine = ComplianceDriftEngine()
        recs = engine._generate_recommendations(drifts, [])
        assert any("comprehensive" in r.lower() for r in recs)


# ---------------------------------------------------------------------------
# Integration / end-to-end tests
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_workflow(self):
        """End-to-end: secure component drifts on all checks."""
        comp = _secure_comp("db-primary")
        graph = _graph(comp)
        baselines = [
            _baseline(fw=ComplianceFramework.SOC2, ts="2025-01-01", score=95.0, sid="s1"),
            _baseline(fw=ComplianceFramework.SOC2, ts="2025-02-01", score=90.0, sid="s2"),
        ]
        state = {
            "db-primary": {
                "encryption_at_rest": False,
                "encryption_in_transit": False,
                "logging_enabled": False,
                "auth_required": False,
                "backup_enabled": False,
                "network_segmented": False,
                "waf_protected": False,
                "rate_limiting": False,
                "ids_monitored": False,
            }
        }
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, state)

        assert report.total_controls_drifted >= 9
        assert report.overall_drift_score > 0
        assert len(report.frameworks_affected) >= 1
        assert len(report.trajectory) >= 1
        assert len(report.remediation_plans) >= 9
        assert len(report.recommendations) >= 1

        # Verify priority ordering
        priorities = [p.priority for p in report.remediation_plans]
        priority_vals = [
            {
                RemediationPriority.IMMEDIATE: 0,
                RemediationPriority.URGENT: 1,
                RemediationPriority.STANDARD: 2,
                RemediationPriority.DEFERRED: 3,
            }[p]
            for p in priorities
        ]
        assert priority_vals == sorted(priority_vals)

    def test_multi_component_multi_framework(self):
        """Multiple components, multiple frameworks."""
        c1 = _secure_comp("app-1")
        c2 = _secure_comp("db-1")
        c3 = _comp("cache-1", ctype=ComponentType.CACHE)
        graph = _graph(c1, c2, c3)
        baselines = [
            _baseline(fw=ComplianceFramework.SOC2, sid="s1"),
            _baseline(fw=ComplianceFramework.HIPAA, sid="s2"),
            _baseline(fw=ComplianceFramework.PCI_DSS, sid="s3"),
        ]
        state = {
            "app-1": {"encryption_at_rest": False},
            "db-1": {"logging_enabled": False, "backup_enabled": False},
        }
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, state)

        assert report.total_controls_drifted >= 3
        assert len(report.frameworks_affected) == 3
        comp_ids = {d.component_id for d in report.drifts}
        assert "app-1" in comp_ids
        assert "db-1" in comp_ids

    def test_compare_then_detect(self):
        """Combine baseline comparison with drift detection."""
        engine = ComplianceDriftEngine()

        old_bl = _baseline(score=90.0, failing=1, passing=9, ts="2025-01-01", sid="s1")
        new_bl = _baseline(score=70.0, failing=4, passing=6, ts="2025-02-01", sid="s2")

        comparison = engine.compare_baselines(old_bl, new_bl)
        assert len(comparison) >= 1

        comp = _secure_comp("s1")
        graph = _graph(comp)
        report = engine.detect_drift(
            graph,
            [old_bl, new_bl],
            {"s1": {"encryption_at_rest": False}},
        )
        assert report.total_controls_drifted >= 1
        assert len(report.trajectory) >= 1

    def test_database_component_type(self):
        c = Component(id="db1", name="db1", type=ComponentType.DATABASE)
        c.security.encryption_at_rest = True
        c.security.backup_enabled = True
        graph = _graph(c)
        baselines = [_baseline(fw=ComplianceFramework.PCI_DSS)]
        state = {"db1": {"encryption_at_rest": False, "backup_enabled": False}}
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, state)
        assert report.total_controls_drifted >= 2

    def test_load_balancer_component_type(self):
        c = Component(id="lb1", name="lb1", type=ComponentType.LOAD_BALANCER)
        c.security.waf_protected = True
        c.security.rate_limiting = True
        graph = _graph(c)
        baselines = [_baseline(fw=ComplianceFramework.NIST_CSF)]
        state = {"lb1": {"waf_protected": False, "rate_limiting": False}}
        engine = ComplianceDriftEngine()
        report = engine.detect_drift(graph, baselines, state)
        assert report.total_controls_drifted >= 2
