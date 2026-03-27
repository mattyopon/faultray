"""Tests for the Compliance Frameworks Engine (SOC 2, ISO 27001, PCI DSS, DORA, HIPAA, GDPR).

Covers 60+ test cases across all frameworks, edge cases, scoring, and control evaluation logic.
"""
from __future__ import annotations

import pytest

from faultray.simulator.compliance_frameworks import (
    ComplianceControl,
    ComplianceFramework,
    ComplianceFrameworksEngine,
    ComplianceReport,
    ControlStatus,
    InfrastructureEvidence,
    Severity,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def all_true_evidence() -> InfrastructureEvidence:
    """Evidence with all controls enabled — should yield full compliance."""
    return InfrastructureEvidence(
        encryption_at_rest=True,
        encryption_in_transit=True,
        backup_enabled=True,
        backup_tested=True,
        mfa_enabled=True,
        audit_logging=True,
        access_reviews=True,
        network_segmentation=True,
        vulnerability_scanning=True,
        incident_response_plan=True,
        change_management=True,
        monitoring_enabled=True,
        dr_plan=True,
        dr_tested=True,
        data_classification=True,
        retention_policy=True,
    )


@pytest.fixture
def all_false_evidence() -> InfrastructureEvidence:
    """Evidence with nothing enabled — should yield zero compliance."""
    return InfrastructureEvidence()


@pytest.fixture
def partial_evidence() -> InfrastructureEvidence:
    """Partial evidence — some controls enabled."""
    return InfrastructureEvidence(
        encryption_at_rest=True,
        encryption_in_transit=False,
        backup_enabled=True,
        backup_tested=False,
        mfa_enabled=True,
        audit_logging=True,
        access_reviews=False,
        network_segmentation=False,
        vulnerability_scanning=False,
        incident_response_plan=False,
        change_management=False,
        monitoring_enabled=False,
        dr_plan=True,
        dr_tested=False,
        data_classification=True,
        retention_policy=False,
    )


# ---------------------------------------------------------------------------
# InfrastructureEvidence dataclass
# ---------------------------------------------------------------------------


class TestInfrastructureEvidence:
    def test_defaults_are_false(self):
        evidence = InfrastructureEvidence()
        assert evidence.encryption_at_rest is False
        assert evidence.encryption_in_transit is False
        assert evidence.backup_enabled is False
        assert evidence.backup_tested is False
        assert evidence.mfa_enabled is False
        assert evidence.audit_logging is False
        assert evidence.access_reviews is False
        assert evidence.network_segmentation is False
        assert evidence.vulnerability_scanning is False
        assert evidence.incident_response_plan is False
        assert evidence.change_management is False
        assert evidence.monitoring_enabled is False
        assert evidence.dr_plan is False
        assert evidence.dr_tested is False
        assert evidence.data_classification is False
        assert evidence.retention_policy is False

    def test_all_true(self, all_true_evidence):
        e = all_true_evidence
        assert e.encryption_at_rest is True
        assert e.mfa_enabled is True
        assert e.dr_tested is True
        assert e.retention_policy is True

    def test_partial_values(self, partial_evidence):
        e = partial_evidence
        assert e.encryption_at_rest is True
        assert e.encryption_in_transit is False
        assert e.backup_enabled is True
        assert e.backup_tested is False


# ---------------------------------------------------------------------------
# ComplianceControl dataclass
# ---------------------------------------------------------------------------


class TestComplianceControl:
    def test_default_status_is_non_compliant(self):
        ctrl = ComplianceControl(
            control_id="TEST-1",
            framework=ComplianceFramework.SOC2,
            title="Test Control",
            description="A test control",
        )
        assert ctrl.status == ControlStatus.NON_COMPLIANT
        assert ctrl.severity == Severity.MEDIUM
        assert ctrl.evidence == []
        assert ctrl.remediation == ""

    def test_custom_fields(self):
        ctrl = ComplianceControl(
            control_id="PCI-3.5",
            framework=ComplianceFramework.PCI_DSS,
            title="Encryption",
            description="Encrypt stored data",
            status=ControlStatus.COMPLIANT,
            severity=Severity.CRITICAL,
            evidence=["AES-256 verified"],
            remediation="",
        )
        assert ctrl.control_id == "PCI-3.5"
        assert ctrl.framework == ComplianceFramework.PCI_DSS
        assert ctrl.status == ControlStatus.COMPLIANT
        assert ctrl.severity == Severity.CRITICAL
        assert len(ctrl.evidence) == 1

    def test_evidence_is_mutable_list(self):
        ctrl = ComplianceControl(
            control_id="X-1",
            framework=ComplianceFramework.DORA,
            title="T",
            description="D",
        )
        ctrl.evidence.append("new evidence")
        assert "new evidence" in ctrl.evidence


# ---------------------------------------------------------------------------
# ComplianceReport dataclass
# ---------------------------------------------------------------------------


class TestComplianceReport:
    def test_empty_report(self):
        report = ComplianceReport(
            framework=ComplianceFramework.SOC2,
            overall_score=0.0,
        )
        assert report.compliant_count == 0
        assert report.partial_count == 0
        assert report.non_compliant_count == 0
        assert report.not_applicable_count == 0
        assert report.controls == []
        assert report.critical_gaps == []
        assert report.recommendations == []

    def test_populated_report(self):
        report = ComplianceReport(
            framework=ComplianceFramework.ISO27001,
            overall_score=75.0,
            compliant_count=6,
            partial_count=1,
            non_compliant_count=1,
            controls=[],
            critical_gaps=["Encryption gap"],
            recommendations=["Enable TLS"],
        )
        assert report.overall_score == 75.0
        assert report.compliant_count == 6
        assert len(report.critical_gaps) == 1


# ---------------------------------------------------------------------------
# Enum values
# ---------------------------------------------------------------------------


class TestEnums:
    def test_compliance_framework_values(self):
        assert ComplianceFramework.DORA.value == "dora"
        assert ComplianceFramework.SOC2.value == "soc2"
        assert ComplianceFramework.ISO27001.value == "iso27001"
        assert ComplianceFramework.PCI_DSS.value == "pci_dss"
        assert ComplianceFramework.HIPAA.value == "hipaa"
        assert ComplianceFramework.GDPR.value == "gdpr"

    def test_control_status_values(self):
        assert ControlStatus.COMPLIANT.value == "compliant"
        assert ControlStatus.PARTIAL.value == "partial"
        assert ControlStatus.NON_COMPLIANT.value == "non_compliant"
        assert ControlStatus.NOT_APPLICABLE.value == "not_applicable"

    def test_severity_values(self):
        assert Severity.CRITICAL.value == "critical"
        assert Severity.HIGH.value == "high"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.LOW.value == "low"
        assert Severity.INFO.value == "info"

    def test_framework_count(self):
        assert len(ComplianceFramework) == 9


# ---------------------------------------------------------------------------
# SOC 2 Assessment
# ---------------------------------------------------------------------------


class TestSOC2Assessment:
    def test_full_compliance(self, all_true_evidence):
        engine = ComplianceFrameworksEngine(all_true_evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        assert report.framework == ComplianceFramework.SOC2
        assert report.overall_score == 100.0
        assert report.compliant_count == 8
        assert report.non_compliant_count == 0
        assert report.partial_count == 0

    def test_no_compliance(self, all_false_evidence):
        engine = ComplianceFrameworksEngine(all_false_evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        assert report.framework == ComplianceFramework.SOC2
        assert report.overall_score == 0.0
        assert report.non_compliant_count == 8
        assert report.compliant_count == 0

    def test_partial_compliance(self, partial_evidence):
        engine = ComplianceFrameworksEngine(partial_evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        assert 0 < report.overall_score < 100
        assert report.partial_count > 0

    def test_control_count(self, all_false_evidence):
        engine = ComplianceFrameworksEngine(all_false_evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        assert len(report.controls) == 8

    def test_critical_gaps_generated(self, all_false_evidence):
        engine = ComplianceFrameworksEngine(all_false_evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        assert len(report.critical_gaps) > 0

    def test_recommendations_generated(self, all_false_evidence):
        engine = ComplianceFrameworksEngine(all_false_evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        assert len(report.recommendations) > 0

    def test_encryption_control_mapping(self):
        evidence = InfrastructureEvidence(encryption_at_rest=True, encryption_in_transit=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        enc_ctrl = [c for c in report.controls if c.control_id == "SOC2-CC6.6"]
        assert len(enc_ctrl) == 1
        assert enc_ctrl[0].status == ControlStatus.COMPLIANT

    def test_encryption_partial(self):
        evidence = InfrastructureEvidence(encryption_at_rest=True, encryption_in_transit=False)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        enc_ctrl = [c for c in report.controls if c.control_id == "SOC2-CC6.6"]
        assert enc_ctrl[0].status == ControlStatus.PARTIAL

    def test_access_control_full(self):
        evidence = InfrastructureEvidence(mfa_enabled=True, access_reviews=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        access_ctrl = [c for c in report.controls if c.control_id == "SOC2-CC6.1"]
        assert access_ctrl[0].status == ControlStatus.COMPLIANT

    def test_access_control_partial(self):
        evidence = InfrastructureEvidence(mfa_enabled=True, access_reviews=False)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        access_ctrl = [c for c in report.controls if c.control_id == "SOC2-CC6.1"]
        assert access_ctrl[0].status == ControlStatus.PARTIAL

    def test_monitoring_control(self):
        evidence = InfrastructureEvidence(audit_logging=True, monitoring_enabled=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        mon_ctrl = [c for c in report.controls if c.control_id == "SOC2-CC7.2"]
        assert mon_ctrl[0].status == ControlStatus.COMPLIANT

    def test_incident_response_control(self):
        evidence = InfrastructureEvidence(incident_response_plan=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        ir_ctrl = [c for c in report.controls if c.control_id == "SOC2-CC7.3"]
        assert ir_ctrl[0].status == ControlStatus.COMPLIANT

    def test_change_management_control(self):
        evidence = InfrastructureEvidence(change_management=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        cm_ctrl = [c for c in report.controls if c.control_id == "SOC2-CC8.1"]
        assert cm_ctrl[0].status == ControlStatus.COMPLIANT

    def test_backup_recovery_full(self):
        evidence = InfrastructureEvidence(backup_enabled=True, backup_tested=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        bk_ctrl = [c for c in report.controls if c.control_id == "SOC2-A1.2"]
        assert bk_ctrl[0].status == ControlStatus.COMPLIANT

    def test_backup_recovery_partial(self):
        evidence = InfrastructureEvidence(backup_enabled=True, backup_tested=False)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        bk_ctrl = [c for c in report.controls if c.control_id == "SOC2-A1.2"]
        assert bk_ctrl[0].status == ControlStatus.PARTIAL

    def test_network_security_control(self):
        evidence = InfrastructureEvidence(network_segmentation=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        net_ctrl = [c for c in report.controls if c.control_id == "SOC2-CC6.7"]
        assert net_ctrl[0].status == ControlStatus.COMPLIANT

    def test_vuln_management_control(self):
        evidence = InfrastructureEvidence(vulnerability_scanning=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        vuln_ctrl = [c for c in report.controls if c.control_id == "SOC2-CC7.1"]
        assert vuln_ctrl[0].status == ControlStatus.COMPLIANT


# ---------------------------------------------------------------------------
# ISO 27001 Assessment
# ---------------------------------------------------------------------------


class TestISO27001Assessment:
    def test_full_compliance(self, all_true_evidence):
        engine = ComplianceFrameworksEngine(all_true_evidence)
        report = engine.assess(ComplianceFramework.ISO27001)
        assert report.framework == ComplianceFramework.ISO27001
        assert report.overall_score == 100.0
        assert report.compliant_count == 8

    def test_no_compliance(self, all_false_evidence):
        engine = ComplianceFrameworksEngine(all_false_evidence)
        report = engine.assess(ComplianceFramework.ISO27001)
        assert report.overall_score == 0.0
        assert report.non_compliant_count == 8

    def test_partial_compliance(self, partial_evidence):
        engine = ComplianceFrameworksEngine(partial_evidence)
        report = engine.assess(ComplianceFramework.ISO27001)
        assert 0 < report.overall_score < 100

    def test_control_count(self, all_false_evidence):
        engine = ComplianceFrameworksEngine(all_false_evidence)
        report = engine.assess(ComplianceFramework.ISO27001)
        assert len(report.controls) == 8

    def test_cryptography_control(self):
        evidence = InfrastructureEvidence(encryption_at_rest=True, encryption_in_transit=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.ISO27001)
        crypto = [c for c in report.controls if c.control_id == "ISO-A.8.24"]
        assert crypto[0].status == ControlStatus.COMPLIANT

    def test_logging_control(self):
        evidence = InfrastructureEvidence(audit_logging=True, monitoring_enabled=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.ISO27001)
        log_ctrl = [c for c in report.controls if c.control_id == "ISO-A.8.15"]
        assert log_ctrl[0].status == ControlStatus.COMPLIANT

    def test_access_control(self):
        evidence = InfrastructureEvidence(mfa_enabled=True, access_reviews=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.ISO27001)
        access_ctrl = [c for c in report.controls if c.control_id == "ISO-A.5.15"]
        assert access_ctrl[0].status == ControlStatus.COMPLIANT

    def test_backup_control(self):
        evidence = InfrastructureEvidence(backup_enabled=True, backup_tested=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.ISO27001)
        bk_ctrl = [c for c in report.controls if c.control_id == "ISO-A.8.13"]
        assert bk_ctrl[0].status == ControlStatus.COMPLIANT

    def test_critical_gaps_for_no_compliance(self, all_false_evidence):
        engine = ComplianceFrameworksEngine(all_false_evidence)
        report = engine.assess(ComplianceFramework.ISO27001)
        assert len(report.critical_gaps) > 0
        # Critical and high severity controls should be listed
        assert any("Cryptography" in g or "Access Control" in g for g in report.critical_gaps)


# ---------------------------------------------------------------------------
# PCI DSS Assessment
# ---------------------------------------------------------------------------


class TestPCIDSSAssessment:
    def test_full_compliance(self, all_true_evidence):
        engine = ComplianceFrameworksEngine(all_true_evidence)
        report = engine.assess(ComplianceFramework.PCI_DSS)
        assert report.framework == ComplianceFramework.PCI_DSS
        assert report.overall_score == 100.0
        assert report.compliant_count == 8

    def test_no_compliance(self, all_false_evidence):
        engine = ComplianceFrameworksEngine(all_false_evidence)
        report = engine.assess(ComplianceFramework.PCI_DSS)
        assert report.overall_score == 0.0
        assert report.non_compliant_count == 8

    def test_partial_compliance(self, partial_evidence):
        engine = ComplianceFrameworksEngine(partial_evidence)
        report = engine.assess(ComplianceFramework.PCI_DSS)
        assert 0 < report.overall_score < 100

    def test_control_count(self, all_false_evidence):
        engine = ComplianceFrameworksEngine(all_false_evidence)
        report = engine.assess(ComplianceFramework.PCI_DSS)
        assert len(report.controls) == 8

    def test_encryption_stored_data(self):
        evidence = InfrastructureEvidence(encryption_at_rest=True, encryption_in_transit=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.PCI_DSS)
        enc_ctrl = [c for c in report.controls if c.control_id == "PCI-3.5"]
        assert enc_ctrl[0].status == ControlStatus.COMPLIANT

    def test_encryption_in_transit(self):
        evidence = InfrastructureEvidence(encryption_at_rest=True, encryption_in_transit=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.PCI_DSS)
        enc_ctrl = [c for c in report.controls if c.control_id == "PCI-4.1"]
        assert enc_ctrl[0].status == ControlStatus.COMPLIANT

    def test_network_firewall(self):
        evidence = InfrastructureEvidence(network_segmentation=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.PCI_DSS)
        fw_ctrl = [c for c in report.controls if c.control_id == "PCI-1.3"]
        assert fw_ctrl[0].status == ControlStatus.COMPLIANT

    def test_mfa_control(self):
        evidence = InfrastructureEvidence(mfa_enabled=True, access_reviews=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.PCI_DSS)
        mfa_ctrl = [c for c in report.controls if c.control_id == "PCI-8.3"]
        assert mfa_ctrl[0].status == ControlStatus.COMPLIANT

    def test_audit_trail(self):
        evidence = InfrastructureEvidence(audit_logging=True, monitoring_enabled=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.PCI_DSS)
        audit_ctrl = [c for c in report.controls if c.control_id == "PCI-10.2"]
        assert audit_ctrl[0].status == ControlStatus.COMPLIANT

    def test_vuln_scanning(self):
        evidence = InfrastructureEvidence(vulnerability_scanning=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.PCI_DSS)
        scan_ctrl = [c for c in report.controls if c.control_id == "PCI-11.3"]
        assert scan_ctrl[0].status == ControlStatus.COMPLIANT

    def test_incident_response(self):
        evidence = InfrastructureEvidence(incident_response_plan=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.PCI_DSS)
        ir_ctrl = [c for c in report.controls if c.control_id == "PCI-12.10"]
        assert ir_ctrl[0].status == ControlStatus.COMPLIANT

    def test_data_classification(self):
        evidence = InfrastructureEvidence(data_classification=True, retention_policy=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.PCI_DSS)
        dc_ctrl = [c for c in report.controls if c.control_id == "PCI-9.4"]
        assert dc_ctrl[0].status == ControlStatus.COMPLIANT

    def test_critical_gaps_with_all_false(self, all_false_evidence):
        engine = ComplianceFrameworksEngine(all_false_evidence)
        report = engine.assess(ComplianceFramework.PCI_DSS)
        # PCI DSS has 4 CRITICAL severity controls
        assert len(report.critical_gaps) >= 4


# ---------------------------------------------------------------------------
# DORA Assessment
# ---------------------------------------------------------------------------


class TestDORAAssessment:
    def test_full_compliance(self, all_true_evidence):
        engine = ComplianceFrameworksEngine(all_true_evidence)
        report = engine.assess(ComplianceFramework.DORA)
        assert report.framework == ComplianceFramework.DORA
        assert report.overall_score == 100.0
        assert report.compliant_count == 6

    def test_no_compliance(self, all_false_evidence):
        engine = ComplianceFrameworksEngine(all_false_evidence)
        report = engine.assess(ComplianceFramework.DORA)
        assert report.overall_score == 0.0
        assert report.non_compliant_count == 6

    def test_control_count(self, all_false_evidence):
        engine = ComplianceFrameworksEngine(all_false_evidence)
        report = engine.assess(ComplianceFramework.DORA)
        assert len(report.controls) == 6

    def test_dr_control(self):
        evidence = InfrastructureEvidence(dr_plan=True, dr_tested=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.DORA)
        dr_ctrl = [c for c in report.controls if c.control_id == "DORA-DR"]
        assert dr_ctrl[0].status == ControlStatus.COMPLIANT

    def test_dr_partial(self):
        evidence = InfrastructureEvidence(dr_plan=True, dr_tested=False)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.DORA)
        dr_ctrl = [c for c in report.controls if c.control_id == "DORA-DR"]
        assert dr_ctrl[0].status == ControlStatus.PARTIAL

    def test_encryption_control(self):
        evidence = InfrastructureEvidence(encryption_at_rest=True, encryption_in_transit=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.DORA)
        enc_ctrl = [c for c in report.controls if c.control_id == "DORA-ENCRYPT"]
        assert enc_ctrl[0].status == ControlStatus.COMPLIANT

    def test_incident_reporting(self):
        evidence = InfrastructureEvidence(incident_response_plan=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.DORA)
        inc_ctrl = [c for c in report.controls if c.control_id == "DORA-17"]
        assert inc_ctrl[0].status == ControlStatus.COMPLIANT


# ---------------------------------------------------------------------------
# HIPAA Assessment
# ---------------------------------------------------------------------------


class TestHIPAAAssessment:
    def test_full_compliance(self, all_true_evidence):
        engine = ComplianceFrameworksEngine(all_true_evidence)
        report = engine.assess(ComplianceFramework.HIPAA)
        assert report.framework == ComplianceFramework.HIPAA
        assert report.overall_score == 100.0
        assert report.compliant_count == 5

    def test_no_compliance(self, all_false_evidence):
        engine = ComplianceFrameworksEngine(all_false_evidence)
        report = engine.assess(ComplianceFramework.HIPAA)
        assert report.overall_score == 0.0
        assert report.non_compliant_count == 5

    def test_control_count(self, all_false_evidence):
        engine = ComplianceFrameworksEngine(all_false_evidence)
        report = engine.assess(ComplianceFramework.HIPAA)
        assert len(report.controls) == 5

    def test_access_control(self):
        evidence = InfrastructureEvidence(mfa_enabled=True, access_reviews=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.HIPAA)
        ac = [c for c in report.controls if c.control_id == "HIPAA-164.312a"]
        assert ac[0].status == ControlStatus.COMPLIANT

    def test_transmission_security(self):
        evidence = InfrastructureEvidence(encryption_at_rest=True, encryption_in_transit=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.HIPAA)
        ts = [c for c in report.controls if c.control_id == "HIPAA-164.312e"]
        assert ts[0].status == ControlStatus.COMPLIANT

    def test_audit_controls(self):
        evidence = InfrastructureEvidence(audit_logging=True, monitoring_enabled=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.HIPAA)
        audit = [c for c in report.controls if c.control_id == "HIPAA-164.312b"]
        assert audit[0].status == ControlStatus.COMPLIANT

    def test_contingency_plan(self):
        evidence = InfrastructureEvidence(backup_enabled=True, backup_tested=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.HIPAA)
        cp = [c for c in report.controls if c.control_id == "HIPAA-164.308a7"]
        assert cp[0].status == ControlStatus.COMPLIANT

    def test_integrity_control_partial(self):
        # "integrity" matches the integrity category, monitoring gives partial
        evidence = InfrastructureEvidence(monitoring_enabled=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.HIPAA)
        integrity = [c for c in report.controls if c.control_id == "HIPAA-164.312c"]
        assert integrity[0].status == ControlStatus.PARTIAL

    def test_integrity_control_compliant(self):
        evidence = InfrastructureEvidence(monitoring_enabled=True, audit_logging=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.HIPAA)
        integrity = [c for c in report.controls if c.control_id == "HIPAA-164.312c"]
        assert integrity[0].status == ControlStatus.COMPLIANT


# ---------------------------------------------------------------------------
# GDPR Assessment
# ---------------------------------------------------------------------------


class TestGDPRAssessment:
    def test_full_compliance(self, all_true_evidence):
        engine = ComplianceFrameworksEngine(all_true_evidence)
        report = engine.assess(ComplianceFramework.GDPR)
        assert report.framework == ComplianceFramework.GDPR
        assert report.overall_score == 100.0
        assert report.compliant_count == 6

    def test_no_compliance(self, all_false_evidence):
        engine = ComplianceFrameworksEngine(all_false_evidence)
        report = engine.assess(ComplianceFramework.GDPR)
        assert report.overall_score == 0.0
        assert report.non_compliant_count == 6

    def test_control_count(self, all_false_evidence):
        engine = ComplianceFrameworksEngine(all_false_evidence)
        report = engine.assess(ComplianceFramework.GDPR)
        assert len(report.controls) == 6

    def test_encryption_control(self):
        evidence = InfrastructureEvidence(encryption_at_rest=True, encryption_in_transit=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.GDPR)
        enc = [c for c in report.controls if c.control_id == "GDPR-ENCRYPT"]
        assert enc[0].status == ControlStatus.COMPLIANT

    def test_audit_logging(self):
        evidence = InfrastructureEvidence(audit_logging=True, monitoring_enabled=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.GDPR)
        audit = [c for c in report.controls if c.control_id == "GDPR-AUDIT"]
        assert audit[0].status == ControlStatus.COMPLIANT

    def test_data_classification(self):
        evidence = InfrastructureEvidence(data_classification=True, retention_policy=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.GDPR)
        dc = [c for c in report.controls if c.control_id == "GDPR-DATA-CLASS"]
        assert dc[0].status == ControlStatus.COMPLIANT

    def test_data_classification_partial(self):
        evidence = InfrastructureEvidence(data_classification=True, retention_policy=False)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.GDPR)
        dc = [c for c in report.controls if c.control_id == "GDPR-DATA-CLASS"]
        assert dc[0].status == ControlStatus.PARTIAL

    def test_data_retention(self):
        evidence = InfrastructureEvidence(data_classification=True, retention_policy=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.GDPR)
        ret = [c for c in report.controls if c.control_id == "GDPR-RETENTION"]
        assert ret[0].status == ControlStatus.COMPLIANT

    def test_breach_notification_compliant(self):
        evidence = InfrastructureEvidence(incident_response_plan=True, monitoring_enabled=True)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.GDPR)
        bn = [c for c in report.controls if c.control_id == "GDPR-33"]
        assert bn[0].status == ControlStatus.COMPLIANT

    def test_breach_notification_partial(self):
        evidence = InfrastructureEvidence(incident_response_plan=True, monitoring_enabled=False)
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.GDPR)
        bn = [c for c in report.controls if c.control_id == "GDPR-33"]
        assert bn[0].status == ControlStatus.PARTIAL


# ---------------------------------------------------------------------------
# assess_all
# ---------------------------------------------------------------------------


class TestAssessAll:
    def test_returns_nine_reports(self, all_true_evidence):
        engine = ComplianceFrameworksEngine(all_true_evidence)
        reports = engine.assess_all()
        assert len(reports) == 9

    def test_all_frameworks_covered(self, all_true_evidence):
        engine = ComplianceFrameworksEngine(all_true_evidence)
        reports = engine.assess_all()
        frameworks = {r.framework for r in reports}
        assert ComplianceFramework.SOC2 in frameworks
        assert ComplianceFramework.ISO27001 in frameworks
        assert ComplianceFramework.PCI_DSS in frameworks
        assert ComplianceFramework.DORA in frameworks
        assert ComplianceFramework.HIPAA in frameworks
        assert ComplianceFramework.GDPR in frameworks

    def test_all_full_compliance(self, all_true_evidence):
        engine = ComplianceFrameworksEngine(all_true_evidence)
        reports = engine.assess_all()
        # AI governance frameworks (METI, ISO42001, AI Promotion) are
        # organizational/policy-based and not fully assessable from
        # infrastructure evidence alone, so exclude them from the
        # 80% threshold check.
        infra_frameworks = {
            ComplianceFramework.SOC2, ComplianceFramework.ISO27001,
            ComplianceFramework.PCI_DSS, ComplianceFramework.DORA,
            ComplianceFramework.HIPAA, ComplianceFramework.GDPR,
        }
        for report in reports:
            if report.framework in infra_frameworks:
                assert report.overall_score >= 80.0, (
                    f"{report.framework} score {report.overall_score} below 80"
                )

    def test_all_zero_compliance(self, all_false_evidence):
        engine = ComplianceFrameworksEngine(all_false_evidence)
        reports = engine.assess_all()
        for report in reports:
            assert report.overall_score == 0.0, (
                f"{report.framework} score {report.overall_score} should be 0"
            )


# ---------------------------------------------------------------------------
# Score Calculation
# ---------------------------------------------------------------------------


class TestScoreCalculation:
    def test_score_100_all_compliant(self, all_true_evidence):
        engine = ComplianceFrameworksEngine(all_true_evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        assert report.overall_score == 100.0

    def test_score_0_all_non_compliant(self, all_false_evidence):
        engine = ComplianceFrameworksEngine(all_false_evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        assert report.overall_score == 0.0

    def test_score_50_with_partial_only(self):
        # Create evidence that results in all partial for a framework
        # For SOC2 encryption: encryption_at_rest=True, encryption_in_transit=False -> partial
        evidence = InfrastructureEvidence(
            encryption_at_rest=True, encryption_in_transit=False,
            backup_enabled=True, backup_tested=False,
            mfa_enabled=True, access_reviews=False,
            audit_logging=True, monitoring_enabled=False,
        )
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        # partial controls contribute 0.5 each
        assert 0 < report.overall_score < 100

    def test_score_rounding(self, all_true_evidence):
        engine = ComplianceFrameworksEngine(all_true_evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        # Score should be a float rounded to 1 decimal
        assert report.overall_score == round(report.overall_score, 1)

    def test_score_with_mixed_statuses(self):
        evidence = InfrastructureEvidence(
            encryption_at_rest=True,
            encryption_in_transit=True,
            mfa_enabled=True,
            access_reviews=True,
        )
        engine = ComplianceFrameworksEngine(evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        # 2 compliant out of 8 = 25%
        assert report.overall_score == 25.0


# ---------------------------------------------------------------------------
# _evaluate_controls logic
# ---------------------------------------------------------------------------


class TestEvaluateControls:
    def test_encryption_mapping_compliant(self):
        evidence = InfrastructureEvidence(encryption_at_rest=True, encryption_in_transit=True)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="ENCRYPT-TEST",
            framework=ComplianceFramework.SOC2,
            title="Encryption Test",
            description="Test encryption mapping",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.COMPLIANT
        assert len(ctrl.evidence) == 1

    def test_encryption_mapping_partial(self):
        evidence = InfrastructureEvidence(encryption_at_rest=True, encryption_in_transit=False)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="ENCRYPT-TEST",
            framework=ComplianceFramework.SOC2,
            title="Enc",
            description="Enc",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.PARTIAL

    def test_backup_mapping_compliant(self):
        evidence = InfrastructureEvidence(backup_enabled=True, backup_tested=True)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="BACKUP-TEST",
            framework=ComplianceFramework.SOC2,
            title="Backup",
            description="Backup",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.COMPLIANT

    def test_backup_mapping_partial(self):
        evidence = InfrastructureEvidence(backup_enabled=True, backup_tested=False)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="BACKUP-TEST",
            framework=ComplianceFramework.SOC2,
            title="Backup",
            description="Backup",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.PARTIAL

    def test_auth_access_mapping_compliant(self):
        evidence = InfrastructureEvidence(mfa_enabled=True, access_reviews=True)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="AUTH-TEST",
            framework=ComplianceFramework.SOC2,
            title="Auth",
            description="Auth",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.COMPLIANT

    def test_auth_access_mapping_partial(self):
        evidence = InfrastructureEvidence(mfa_enabled=True, access_reviews=False)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="ACCESS-TEST",
            framework=ComplianceFramework.SOC2,
            title="Access",
            description="Access",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.PARTIAL

    def test_monitoring_mapping_compliant(self):
        evidence = InfrastructureEvidence(audit_logging=True, monitoring_enabled=True)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="MONITOR-TEST",
            framework=ComplianceFramework.SOC2,
            title="Monitor",
            description="Monitor",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.COMPLIANT

    def test_monitoring_mapping_partial(self):
        evidence = InfrastructureEvidence(audit_logging=True, monitoring_enabled=False)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="AUDIT-TEST",
            framework=ComplianceFramework.SOC2,
            title="Audit",
            description="Audit",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.PARTIAL

    def test_network_segment_mapping(self):
        evidence = InfrastructureEvidence(network_segmentation=True)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="NETWORK-SEG",
            framework=ComplianceFramework.SOC2,
            title="Net",
            description="Net",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.COMPLIANT

    def test_vuln_scan_mapping(self):
        evidence = InfrastructureEvidence(vulnerability_scanning=True)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="VULN-SCAN",
            framework=ComplianceFramework.SOC2,
            title="Vuln",
            description="Vuln",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.COMPLIANT

    def test_incident_mapping(self):
        evidence = InfrastructureEvidence(incident_response_plan=True)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="INCIDENT-PLAN",
            framework=ComplianceFramework.SOC2,
            title="IR",
            description="IR",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.COMPLIANT

    def test_change_mapping(self):
        evidence = InfrastructureEvidence(change_management=True)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="CHANGE-MGMT",
            framework=ComplianceFramework.SOC2,
            title="Change",
            description="Change",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.COMPLIANT

    def test_data_classification_mapping_compliant(self):
        evidence = InfrastructureEvidence(data_classification=True, retention_policy=True)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="DATA-CLASSIFICATION",
            framework=ComplianceFramework.SOC2,
            title="DataClass",
            description="Data classification",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.COMPLIANT

    def test_data_classification_mapping_partial(self):
        evidence = InfrastructureEvidence(data_classification=True, retention_policy=False)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="DATA-CLASSIFICATION",
            framework=ComplianceFramework.SOC2,
            title="DataClass",
            description="Data classification",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.PARTIAL

    def test_dr_mapping_compliant(self):
        evidence = InfrastructureEvidence(dr_plan=True, dr_tested=True)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="DR-PLAN",
            framework=ComplianceFramework.DORA,
            title="DR",
            description="DR",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.COMPLIANT

    def test_dr_mapping_partial(self):
        evidence = InfrastructureEvidence(dr_plan=True, dr_tested=False)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="DR-PLAN",
            framework=ComplianceFramework.DORA,
            title="DR",
            description="DR",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.PARTIAL

    def test_unmatched_control_stays_non_compliant(self):
        evidence = InfrastructureEvidence()
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="UNKNOWN-PATTERN-XYZ",
            framework=ComplianceFramework.SOC2,
            title="Unknown",
            description="No pattern match",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.NON_COMPLIANT


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_default_evidence_creates_engine(self):
        engine = ComplianceFrameworksEngine()
        assert engine.evidence is not None
        assert engine.evidence.encryption_at_rest is False

    def test_none_evidence_uses_defaults(self):
        engine = ComplianceFrameworksEngine(None)
        assert engine.evidence.mfa_enabled is False

    def test_assess_returns_proper_type(self, all_true_evidence):
        engine = ComplianceFrameworksEngine(all_true_evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        assert isinstance(report, ComplianceReport)
        assert isinstance(report.controls[0], ComplianceControl)

    def test_critical_gaps_limited_to_5(self, all_false_evidence):
        engine = ComplianceFrameworksEngine(all_false_evidence)
        report = engine.assess(ComplianceFramework.PCI_DSS)
        assert len(report.critical_gaps) <= 5

    def test_recommendations_limited_to_10(self, all_false_evidence):
        engine = ComplianceFrameworksEngine(all_false_evidence)
        report = engine.assess(ComplianceFramework.SOC2)
        assert len(report.recommendations) <= 10

    def test_all_controls_have_framework_field(self, all_true_evidence):
        engine = ComplianceFrameworksEngine(all_true_evidence)
        for fw in ComplianceFramework:
            report = engine.assess(fw)
            for ctrl in report.controls:
                assert ctrl.framework == fw

    def test_all_controls_have_remediation(self, all_false_evidence):
        engine = ComplianceFrameworksEngine(all_false_evidence)
        for fw in ComplianceFramework:
            report = engine.assess(fw)
            for ctrl in report.controls:
                assert ctrl.remediation != "", (
                    f"{ctrl.control_id} has empty remediation"
                )

    def test_evidence_fields_are_independent(self):
        """Changing one evidence field should not affect others."""
        evidence = InfrastructureEvidence(encryption_at_rest=True)
        assert evidence.encryption_at_rest is True
        assert evidence.encryption_in_transit is False
        assert evidence.mfa_enabled is False

    def test_multiple_engine_instances_independent(self):
        """Two engines with different evidence should produce different results."""
        engine1 = ComplianceFrameworksEngine(InfrastructureEvidence())
        engine2 = ComplianceFrameworksEngine(InfrastructureEvidence(
            encryption_at_rest=True, encryption_in_transit=True,
            mfa_enabled=True, access_reviews=True,
        ))
        report1 = engine1.assess(ComplianceFramework.SOC2)
        report2 = engine2.assess(ComplianceFramework.SOC2)
        assert report1.overall_score < report2.overall_score

    def test_recovery_keyword_in_backup_controls(self):
        """Controls with 'recovery' in ID should use backup evidence mapping."""
        evidence = InfrastructureEvidence(backup_enabled=True, backup_tested=True)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="RECOVERY-PLAN",
            framework=ComplianceFramework.SOC2,
            title="Recovery",
            description="Recovery",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.COMPLIANT

    def test_continuity_keyword_in_backup_controls(self):
        """Controls with 'continuity' in ID should use backup evidence mapping."""
        evidence = InfrastructureEvidence(backup_enabled=True, backup_tested=True)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="CONTINUITY-PLAN",
            framework=ComplianceFramework.SOC2,
            title="Continuity",
            description="Continuity",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.COMPLIANT

    def test_firewall_keyword_maps_to_network(self):
        """Controls with 'firewall' should use network segmentation evidence."""
        evidence = InfrastructureEvidence(network_segmentation=True)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="FIREWALL-RULES",
            framework=ComplianceFramework.PCI_DSS,
            title="Firewall",
            description="FW",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.COMPLIANT

    def test_patch_keyword_maps_to_vuln(self):
        """Controls with 'patch' should use vulnerability scanning evidence."""
        evidence = InfrastructureEvidence(vulnerability_scanning=True)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="PATCH-MGMT",
            framework=ComplianceFramework.ISO27001,
            title="Patching",
            description="Patching",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.COMPLIANT

    def test_identity_keyword_maps_to_auth(self):
        """Controls with 'identity' should use auth/access evidence."""
        evidence = InfrastructureEvidence(mfa_enabled=True, access_reviews=True)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="IDENTITY-MGMT",
            framework=ComplianceFramework.SOC2,
            title="Identity",
            description="Identity",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.COMPLIANT

    def test_disaster_keyword_maps_to_dr(self):
        """Controls with 'disaster' should use DR evidence."""
        evidence = InfrastructureEvidence(dr_plan=True, dr_tested=True)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="DISASTER-PLAN",
            framework=ComplianceFramework.DORA,
            title="Disaster Recovery",
            description="DR",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.COMPLIANT

    def test_crypto_keyword_maps_to_encryption(self):
        """Controls with 'crypto' should use encryption evidence."""
        evidence = InfrastructureEvidence(encryption_at_rest=True, encryption_in_transit=True)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="CRYPTO-POLICY",
            framework=ComplianceFramework.ISO27001,
            title="Crypto",
            description="Crypto",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.COMPLIANT

    def test_retention_keyword_maps_to_data(self):
        """Controls with 'retention' should use data classification evidence."""
        evidence = InfrastructureEvidence(data_classification=True, retention_policy=True)
        engine = ComplianceFrameworksEngine(evidence)
        ctrl = ComplianceControl(
            control_id="RETENTION-POLICY",
            framework=ComplianceFramework.GDPR,
            title="Retention",
            description="Retention",
        )
        engine._evaluate_controls([ctrl])
        assert ctrl.status == ControlStatus.COMPLIANT
