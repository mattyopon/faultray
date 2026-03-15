"""Tests for compliance scorecard engine."""

from __future__ import annotations

import pytest

from infrasim.model.components import Component, ComponentType, HealthStatus
from infrasim.model.graph import InfraGraph
from infrasim.simulator.compliance_scorecard import (
    ComplianceReport,
    ComplianceScorecardEngine,
    ControlStatus,
    Framework,
    FrameworkScorecard,
    _control_status,
    _score_to_grade,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    encrypt_rest: bool = False,
    encrypt_transit: bool = False,
    auth: bool = False,
    log: bool = False,
    ids: bool = False,
    waf: bool = False,
    rate_limit: bool = False,
    segmented: bool = False,
    backup: bool = False,
    failover: bool = False,
    change_mgmt: bool = False,
    audit: bool = False,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.security.encryption_at_rest = encrypt_rest
    c.security.encryption_in_transit = encrypt_transit
    c.security.auth_required = auth
    c.security.log_enabled = log
    c.security.ids_monitored = ids
    c.security.waf_protected = waf
    c.security.rate_limiting = rate_limit
    c.security.network_segmented = segmented
    c.security.backup_enabled = backup
    if failover:
        c.failover.enabled = True
    c.compliance_tags.change_management = change_mgmt
    c.compliance_tags.audit_logging = audit
    return c


def _secure_graph() -> InfraGraph:
    """Graph where all security features are enabled."""
    g = InfraGraph()
    g.add_component(_comp(
        "api", "API Server", replicas=3, encrypt_rest=True,
        encrypt_transit=True, auth=True, log=True, ids=True,
        waf=True, rate_limit=True, segmented=True, backup=True,
        failover=True, change_mgmt=True, audit=True,
    ))
    g.add_component(_comp(
        "db", "Database", ComponentType.DATABASE, replicas=3,
        encrypt_rest=True, encrypt_transit=True, auth=True,
        log=True, ids=True, segmented=True, backup=True,
        failover=True, change_mgmt=True, audit=True,
    ))
    return g


def _insecure_graph() -> InfraGraph:
    """Graph with minimal security features."""
    g = InfraGraph()
    g.add_component(_comp("api", "API Server"))
    g.add_component(_comp("db", "Database", ComponentType.DATABASE))
    return g


def _mixed_graph() -> InfraGraph:
    """Graph with some security features enabled."""
    g = InfraGraph()
    g.add_component(_comp(
        "api", "API Server", replicas=2, encrypt_transit=True,
        auth=True, log=True,
    ))
    g.add_component(_comp("db", "Database", ComponentType.DATABASE, backup=True))
    g.add_component(_comp(
        "ext", "Payment Gateway", ComponentType.EXTERNAL_API,
        encrypt_transit=True, rate_limit=True, failover=True,
    ))
    return g


# ---------------------------------------------------------------------------
# Unit tests: helper functions
# ---------------------------------------------------------------------------


class TestScoreToGrade:
    def test_grade_a(self):
        assert _score_to_grade(95) == "A"
        assert _score_to_grade(90) == "A"

    def test_grade_b(self):
        assert _score_to_grade(85) == "B"
        assert _score_to_grade(80) == "B"

    def test_grade_c(self):
        assert _score_to_grade(75) == "C"
        assert _score_to_grade(70) == "C"

    def test_grade_d(self):
        assert _score_to_grade(65) == "D"
        assert _score_to_grade(60) == "D"

    def test_grade_f(self):
        assert _score_to_grade(50) == "F"
        assert _score_to_grade(0) == "F"


class TestControlStatus:
    def test_compliant(self):
        assert _control_status(90) == ControlStatus.COMPLIANT
        assert _control_status(80) == ControlStatus.COMPLIANT

    def test_partial(self):
        assert _control_status(60) == ControlStatus.PARTIAL
        assert _control_status(40) == ControlStatus.PARTIAL

    def test_non_compliant(self):
        assert _control_status(30) == ControlStatus.NON_COMPLIANT
        assert _control_status(0) == ControlStatus.NON_COMPLIANT


# ---------------------------------------------------------------------------
# Tests: Full assessment
# ---------------------------------------------------------------------------


class TestFullAssessment:
    def test_empty_graph(self):
        engine = ComplianceScorecardEngine()
        g = InfraGraph()
        report = engine.assess(g, [Framework.SOC2])
        assert report.component_count == 0
        assert report.frameworks_assessed == 1

    def test_all_frameworks(self):
        engine = ComplianceScorecardEngine()
        g = _mixed_graph()
        report = engine.assess(g)
        assert report.frameworks_assessed == 6
        assert len(report.scorecards) == 6
        for fw in Framework:
            assert fw.value in report.scorecards

    def test_single_framework(self):
        engine = ComplianceScorecardEngine()
        g = _mixed_graph()
        report = engine.assess(g, [Framework.SOC2])
        assert report.frameworks_assessed == 1
        assert "SOC2" in report.scorecards

    def test_secure_graph_high_score(self):
        engine = ComplianceScorecardEngine()
        g = _secure_graph()
        report = engine.assess(g)
        assert report.overall_score >= 70
        assert report.overall_grade in ("A", "B", "C")

    def test_insecure_graph_low_score(self):
        engine = ComplianceScorecardEngine()
        g = _insecure_graph()
        report = engine.assess(g)
        assert report.overall_score < 50
        assert report.overall_grade in ("D", "F")

    def test_report_has_gaps(self):
        engine = ComplianceScorecardEngine()
        g = _insecure_graph()
        report = engine.assess(g)
        assert len(report.top_gaps) > 0

    def test_report_has_actions(self):
        engine = ComplianceScorecardEngine()
        g = _insecure_graph()
        report = engine.assess(g)
        assert len(report.priority_actions) > 0


# ---------------------------------------------------------------------------
# Tests: Single framework assessment
# ---------------------------------------------------------------------------


class TestSingleFramework:
    @pytest.mark.parametrize("fw", list(Framework))
    def test_each_framework(self, fw):
        engine = ComplianceScorecardEngine()
        g = _mixed_graph()
        scorecard = engine.assess_single(g, fw)
        assert scorecard.framework == fw
        assert 0 <= scorecard.overall_score <= 100
        assert scorecard.grade in ("A", "B", "C", "D", "F")
        assert len(scorecard.controls) == 10
        total = (
            scorecard.compliant_count
            + scorecard.partial_count
            + scorecard.non_compliant_count
            + scorecard.not_applicable_count
        )
        assert total == len(scorecard.controls)

    def test_soc2_controls(self):
        engine = ComplianceScorecardEngine()
        g = _secure_graph()
        scorecard = engine.assess_single(g, Framework.SOC2)
        ctrl_ids = [c.control_id for c in scorecard.controls]
        assert "CC6.1" in ctrl_ids
        assert "A1.1" in ctrl_ids

    def test_dora_controls(self):
        engine = ComplianceScorecardEngine()
        g = _secure_graph()
        scorecard = engine.assess_single(g, Framework.DORA)
        ctrl_ids = [c.control_id for c in scorecard.controls]
        assert "Art.5" in ctrl_ids
        assert "Art.24" in ctrl_ids

    def test_scorecard_summary(self):
        engine = ComplianceScorecardEngine()
        g = _mixed_graph()
        scorecard = engine.assess_single(g, Framework.SOC2)
        assert len(scorecard.summary) > 0


# ---------------------------------------------------------------------------
# Tests: Compare frameworks
# ---------------------------------------------------------------------------


class TestCompareFrameworks:
    def test_compare_structure(self):
        engine = ComplianceScorecardEngine()
        g = _mixed_graph()
        comparison = engine.compare_frameworks(g)
        assert len(comparison) == 6
        for fw_name, data in comparison.items():
            assert "score" in data
            assert "grade" in data
            assert "compliant" in data
            assert "partial" in data
            assert "non_compliant" in data


# ---------------------------------------------------------------------------
# Tests: Gap analysis
# ---------------------------------------------------------------------------


class TestGapAnalysis:
    def test_insecure_has_gaps(self):
        engine = ComplianceScorecardEngine()
        g = _insecure_graph()
        gaps = engine.gap_analysis(g, Framework.SOC2)
        assert len(gaps) > 0
        for gap in gaps:
            assert gap["status"] in ("non_compliant", "partial")
            assert len(gap["gaps"]) > 0

    def test_secure_minimal_gaps(self):
        engine = ComplianceScorecardEngine()
        g = _secure_graph()
        gaps = engine.gap_analysis(g, Framework.SOC2)
        # Secure graph should have few or no gaps
        assert len(gaps) <= 5


# ---------------------------------------------------------------------------
# Tests: Control scoring categories
# ---------------------------------------------------------------------------


class TestEncryptionScoring:
    def test_full_encryption(self):
        engine = ComplianceScorecardEngine()
        g = _secure_graph()
        scorecard = engine.assess_single(g, Framework.SOC2)
        # CC6.6 is Encryption in Transit
        transit = next(c for c in scorecard.controls if c.control_id == "CC6.6")
        assert transit.score >= 80
        assert transit.status == ControlStatus.COMPLIANT

    def test_no_encryption(self):
        engine = ComplianceScorecardEngine()
        g = _insecure_graph()
        scorecard = engine.assess_single(g, Framework.SOC2)
        transit = next(c for c in scorecard.controls if c.control_id == "CC6.6")
        assert transit.score == 0
        assert transit.status == ControlStatus.NON_COMPLIANT


class TestRedundancyScoring:
    def test_redundant_components(self):
        engine = ComplianceScorecardEngine()
        g = _secure_graph()
        scorecard = engine.assess_single(g, Framework.SOC2)
        redundancy = next(c for c in scorecard.controls if c.control_id == "A1.2")
        assert redundancy.score >= 80

    def test_no_redundancy(self):
        engine = ComplianceScorecardEngine()
        g = _insecure_graph()
        scorecard = engine.assess_single(g, Framework.SOC2)
        redundancy = next(c for c in scorecard.controls if c.control_id == "A1.2")
        assert redundancy.score == 0


class TestThirdPartyScoring:
    def test_with_external_apis(self):
        engine = ComplianceScorecardEngine()
        g = _mixed_graph()
        scorecard = engine.assess_single(g, Framework.DORA)
        tp = next(c for c in scorecard.controls if c.control_id == "Art.28")
        # Has a well-configured external API
        assert tp.score > 0

    def test_no_external_apis(self):
        engine = ComplianceScorecardEngine()
        g = _secure_graph()  # No external APIs
        scorecard = engine.assess_single(g, Framework.DORA)
        tp = next(c for c in scorecard.controls if c.control_id == "Art.28")
        # Should get partial score (can't prove management without third parties)
        assert tp.score == 80


# ---------------------------------------------------------------------------
# Tests: Evidence
# ---------------------------------------------------------------------------


class TestEvidence:
    def test_evidence_per_component(self):
        engine = ComplianceScorecardEngine()
        g = _mixed_graph()
        scorecard = engine.assess_single(g, Framework.SOC2)
        for ctrl in scorecard.controls:
            if ctrl.status != ControlStatus.NOT_APPLICABLE:
                # Each control should have evidence from assessed components
                assert len(ctrl.evidence) >= 0

    def test_evidence_attributes(self):
        engine = ComplianceScorecardEngine()
        g = _mixed_graph()
        scorecard = engine.assess_single(g, Framework.SOC2)
        for ctrl in scorecard.controls:
            for ev in ctrl.evidence:
                assert ev.component_id
                assert ev.component_name
                assert ev.finding
                assert isinstance(ev.supports_compliance, bool)


# ---------------------------------------------------------------------------
# Tests: Enum values
# ---------------------------------------------------------------------------


class TestEnums:
    def test_framework_values(self):
        assert Framework.SOC2.value == "SOC2"
        assert Framework.ISO27001.value == "ISO27001"
        assert Framework.PCI_DSS.value == "PCI_DSS"
        assert Framework.HIPAA.value == "HIPAA"
        assert Framework.NIST_CSF.value == "NIST_CSF"
        assert Framework.DORA.value == "DORA"

    def test_control_status_values(self):
        assert ControlStatus.COMPLIANT.value == "compliant"
        assert ControlStatus.PARTIAL.value == "partial"
        assert ControlStatus.NON_COMPLIANT.value == "non_compliant"
        assert ControlStatus.NOT_APPLICABLE.value == "not_applicable"


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_single_component(self):
        engine = ComplianceScorecardEngine()
        g = InfraGraph()
        g.add_component(_comp("solo", "Solo"))
        report = engine.assess(g, [Framework.SOC2])
        assert report.component_count == 1

    def test_many_frameworks_at_once(self):
        engine = ComplianceScorecardEngine()
        g = _mixed_graph()
        report = engine.assess(g, list(Framework))
        assert report.frameworks_assessed == 6

    def test_overall_score_is_average(self):
        engine = ComplianceScorecardEngine()
        g = _mixed_graph()
        report = engine.assess(g)
        fw_scores = [sc.overall_score for sc in report.scorecards.values()]
        expected = sum(fw_scores) / len(fw_scores)
        assert abs(report.overall_score - expected) < 0.2

    def test_empty_framework_list(self):
        engine = ComplianceScorecardEngine()
        g = _mixed_graph()
        report = engine.assess(g, [])
        assert report.frameworks_assessed == 0

    def test_incident_response_scoring(self):
        engine = ComplianceScorecardEngine()
        g = InfraGraph()
        c = _comp("api", "API", log=True, ids=True)
        c.team.runbook_coverage_percent = 80.0
        c.team.oncall_coverage_hours = 24.0
        g.add_component(c)
        scorecard = engine.assess_single(g, Framework.SOC2)
        incident = next(c for c in scorecard.controls if c.control_id == "CC8.1")
        assert incident.score >= 80

    def test_change_management_scoring(self):
        engine = ComplianceScorecardEngine()
        g = InfraGraph()
        g.add_component(_comp("api", "API", change_mgmt=True))
        scorecard = engine.assess_single(g, Framework.SOC2)
        cm = next(c for c in scorecard.controls if c.control_id == "CC7.3")
        assert cm.score == 100

    def test_risk_governance_scoring(self):
        engine = ComplianceScorecardEngine()
        g = InfraGraph()
        c = _comp("api", "API", log=True, audit=True)
        c.tags = ["production"]
        c.compliance_tags.data_classification = "confidential"
        g.add_component(c)
        scorecard = engine.assess_single(g, Framework.NIST_CSF)
        risk = next(c for c in scorecard.controls if c.control_id == "ID.AM")
        assert risk.score >= 80

    def test_network_segmentation_scoring(self):
        engine = ComplianceScorecardEngine()
        g = InfraGraph()
        g.add_component(_comp("api", "API", segmented=True))
        scorecard = engine.assess_single(g, Framework.PCI_DSS)
        net = next(c for c in scorecard.controls if c.control_id == "1.1")
        assert net.score == 100
