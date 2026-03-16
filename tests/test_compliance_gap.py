"""Tests for the Compliance Gap Analyzer.

Covers all enum values, all five frameworks (SOC2, HIPAA, PCI-DSS, GDPR,
ISO27001), score calculation, remediation ordering, and edge cases.
"""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    HealthStatus,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.compliance_gap import (
    ComplianceFramework,
    ComplianceGap,
    ComplianceGapAnalyzer,
    ComplianceGapReport,
    ComplianceRequirement,
    ComplianceStatus,
    RemediationPriority,
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
    segmented: bool = False,
    backup: bool = False,
    failover: bool = False,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.security.encryption_at_rest = encrypt_rest
    c.security.encryption_in_transit = encrypt_transit
    c.security.auth_required = auth
    c.security.log_enabled = log
    c.security.ids_monitored = ids
    c.security.waf_protected = waf
    c.security.network_segmented = segmented
    c.security.backup_enabled = backup
    if failover:
        c.failover.enabled = True
    return c


def _fully_compliant_graph() -> InfraGraph:
    """Graph where every security feature is enabled on every component."""
    g = InfraGraph()
    g.add_component(_comp(
        "api", "API Server",
        ctype=ComponentType.APP_SERVER,
        replicas=3,
        encrypt_rest=True, encrypt_transit=True, auth=True,
        log=True, ids=True, waf=True, segmented=True,
        backup=True, failover=True,
    ))
    g.add_component(_comp(
        "db", "PostgreSQL",
        ctype=ComponentType.DATABASE,
        replicas=3,
        encrypt_rest=True, encrypt_transit=True, auth=True,
        log=True, ids=True, waf=False, segmented=True,
        backup=True, failover=True,
    ))
    g.add_component(_comp(
        "cache", "Redis",
        ctype=ComponentType.CACHE,
        replicas=2,
        encrypt_rest=True, encrypt_transit=True, auth=True,
        log=True, ids=True, waf=False, segmented=True,
        backup=True, failover=True,
    ))
    return g


def _minimal_graph() -> InfraGraph:
    """Graph with no security features at all."""
    g = InfraGraph()
    g.add_component(_comp("app", "App", replicas=1))
    g.add_component(_comp("db", "DB", ctype=ComponentType.DATABASE, replicas=1))
    return g


# ---------------------------------------------------------------------------
# Enum value tests
# ---------------------------------------------------------------------------


class TestComplianceFrameworkEnum:
    def test_soc2(self):
        assert ComplianceFramework.SOC2.value == "soc2"

    def test_hipaa(self):
        assert ComplianceFramework.HIPAA.value == "hipaa"

    def test_pci_dss(self):
        assert ComplianceFramework.PCI_DSS.value == "pci_dss"

    def test_gdpr(self):
        assert ComplianceFramework.GDPR.value == "gdpr"

    def test_iso27001(self):
        assert ComplianceFramework.ISO27001.value == "iso27001"

    def test_all_values_count(self):
        assert len(ComplianceFramework) == 5


class TestComplianceStatusEnum:
    def test_compliant(self):
        assert ComplianceStatus.COMPLIANT.value == "compliant"

    def test_partial(self):
        assert ComplianceStatus.PARTIAL.value == "partial"

    def test_non_compliant(self):
        assert ComplianceStatus.NON_COMPLIANT.value == "non_compliant"

    def test_not_applicable(self):
        assert ComplianceStatus.NOT_APPLICABLE.value == "not_applicable"


class TestRemediationPriorityEnum:
    def test_immediate(self):
        assert RemediationPriority.IMMEDIATE.value == "immediate"

    def test_high(self):
        assert RemediationPriority.HIGH.value == "high"

    def test_medium(self):
        assert RemediationPriority.MEDIUM.value == "medium"

    def test_low(self):
        assert RemediationPriority.LOW.value == "low"


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestComplianceRequirement:
    def test_fields(self):
        req = ComplianceRequirement(
            framework=ComplianceFramework.SOC2,
            requirement_id="SOC2-CC6.1",
            description="Encryption at rest",
            category="Security",
        )
        assert req.framework == ComplianceFramework.SOC2
        assert req.requirement_id == "SOC2-CC6.1"
        assert req.description == "Encryption at rest"
        assert req.category == "Security"


class TestComplianceGapDataclass:
    def test_fields(self):
        req = ComplianceRequirement(
            ComplianceFramework.HIPAA, "HIPAA-164.312a",
            "Access control", "Access Control",
        )
        gap = ComplianceGap(
            requirement=req,
            status=ComplianceStatus.NON_COMPLIANT,
            component_id="db-1",
            component_name="Primary DB",
            finding="No access control",
            remediation="Enable auth",
            priority=RemediationPriority.IMMEDIATE,
        )
        assert gap.requirement.framework == ComplianceFramework.HIPAA
        assert gap.status == ComplianceStatus.NON_COMPLIANT
        assert gap.component_id == "db-1"
        assert gap.priority == RemediationPriority.IMMEDIATE


class TestComplianceGapReportDataclass:
    def test_default_values(self):
        report = ComplianceGapReport(framework=ComplianceFramework.SOC2)
        assert report.total_requirements == 0
        assert report.compliant_count == 0
        assert report.compliance_score == 0.0
        assert report.gaps == []
        assert report.critical_gaps == []
        assert report.remediation_plan == []

    def test_with_values(self):
        report = ComplianceGapReport(
            framework=ComplianceFramework.GDPR,
            total_requirements=10,
            compliant_count=7,
            partial_count=2,
            non_compliant_count=1,
            compliance_score=80.0,
        )
        assert report.framework == ComplianceFramework.GDPR
        assert report.total_requirements == 10
        assert report.compliant_count == 7


# ---------------------------------------------------------------------------
# SOC2 analysis tests
# ---------------------------------------------------------------------------


class TestSOC2Analysis:
    def test_fully_compliant_infra(self):
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(_fully_compliant_graph(), ComplianceFramework.SOC2)
        assert report.framework == ComplianceFramework.SOC2
        assert report.compliance_score == 100.0
        assert report.non_compliant_count == 0
        assert len(report.gaps) == 0

    def test_non_encrypted_database_detected(self):
        g = InfraGraph()
        g.add_component(_comp(
            "db", "MainDB", ctype=ComponentType.DATABASE,
            replicas=2, log=True, auth=True, ids=True,
            segmented=True, backup=True, failover=True,
            encrypt_rest=False, encrypt_transit=True,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.SOC2)
        enc_gaps = [gap for gap in report.gaps if "encryption at rest" in gap.finding.lower()]
        assert len(enc_gaps) >= 1
        assert enc_gaps[0].status == ComplianceStatus.NON_COMPLIANT

    def test_missing_backup_gap(self):
        g = InfraGraph()
        g.add_component(_comp(
            "db", "MainDB", ctype=ComponentType.DATABASE,
            replicas=2, encrypt_rest=True, encrypt_transit=True,
            log=True, auth=True, ids=True, segmented=True,
            backup=False, failover=True,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.SOC2)
        backup_gaps = [gap for gap in report.gaps if "backup" in gap.finding.lower()]
        assert len(backup_gaps) >= 1

    def test_missing_monitoring(self):
        g = InfraGraph()
        g.add_component(_comp(
            "api", "API", replicas=2, encrypt_rest=True,
            encrypt_transit=True, auth=True, log=False,
            ids=True, waf=True, segmented=True, backup=True,
            failover=True,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.SOC2)
        log_gaps = [gap for gap in report.gaps if "logging" in gap.finding.lower() or "monitoring" in gap.finding.lower()]
        assert len(log_gaps) >= 1

    def test_missing_access_control(self):
        g = InfraGraph()
        g.add_component(_comp(
            "api", "API", replicas=2, encrypt_rest=True,
            encrypt_transit=True, auth=False, log=True,
            ids=True, waf=True, segmented=True, backup=True,
            failover=True,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.SOC2)
        auth_gaps = [gap for gap in report.gaps if "access control" in gap.finding.lower() or "auth" in gap.finding.lower()]
        assert len(auth_gaps) >= 1

    def test_missing_failover(self):
        g = InfraGraph()
        g.add_component(_comp(
            "db", "Database", ctype=ComponentType.DATABASE,
            replicas=2, encrypt_rest=True, encrypt_transit=True,
            auth=True, log=True, ids=True, segmented=True,
            backup=True, failover=False,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.SOC2)
        fo_gaps = [gap for gap in report.gaps if "failover" in gap.finding.lower()]
        assert len(fo_gaps) >= 1

    def test_single_replica_gap(self):
        g = InfraGraph()
        g.add_component(_comp(
            "api", "API", replicas=1, encrypt_rest=True,
            encrypt_transit=True, auth=True, log=True,
            ids=True, waf=True, segmented=True, backup=True,
            failover=True,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.SOC2)
        replica_gaps = [gap for gap in report.gaps if "replica" in gap.finding.lower()]
        assert len(replica_gaps) >= 1


# ---------------------------------------------------------------------------
# HIPAA analysis tests
# ---------------------------------------------------------------------------


class TestHIPAAAnalysis:
    def test_fully_compliant(self):
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(_fully_compliant_graph(), ComplianceFramework.HIPAA)
        assert report.framework == ComplianceFramework.HIPAA
        assert report.compliance_score == 100.0

    def test_phi_without_encryption(self):
        g = InfraGraph()
        g.add_component(_comp(
            "db", "PHI Database", ctype=ComponentType.DATABASE,
            replicas=2, encrypt_rest=False, encrypt_transit=False,
            auth=True, log=True, backup=True, failover=True,
            ids=True, segmented=True,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.HIPAA)
        assert report.non_compliant_count > 0
        enc_gaps = [g for g in report.gaps if "encryption" in g.finding.lower()]
        assert len(enc_gaps) >= 1

    def test_hipaa_access_control(self):
        g = InfraGraph()
        g.add_component(_comp(
            "api", "API", replicas=2, encrypt_rest=True,
            encrypt_transit=True, auth=False, log=True,
            backup=True, failover=True, ids=True, segmented=True,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.HIPAA)
        auth_gaps = [gap for gap in report.gaps if "auth" in gap.finding.lower() or "access control" in gap.finding.lower()]
        assert len(auth_gaps) >= 1

    def test_hipaa_audit_logging(self):
        g = InfraGraph()
        g.add_component(_comp(
            "db", "DB", ctype=ComponentType.DATABASE,
            replicas=2, encrypt_rest=True, encrypt_transit=True,
            auth=True, log=False, backup=True, failover=True,
            ids=True, segmented=True,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.HIPAA)
        log_gaps = [g for g in report.gaps if "logging" in g.finding.lower() or "monitoring" in g.finding.lower()]
        assert len(log_gaps) >= 1

    def test_hipaa_network_segmentation(self):
        g = InfraGraph()
        g.add_component(_comp(
            "api", "API", replicas=2, encrypt_rest=True,
            encrypt_transit=True, auth=True, log=True,
            backup=True, failover=True, ids=True, segmented=False,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.HIPAA)
        seg_gaps = [gap for gap in report.gaps if "segmentation" in gap.finding.lower()]
        assert len(seg_gaps) >= 1

    def test_hipaa_backup_dr(self):
        g = InfraGraph()
        g.add_component(_comp(
            "db", "DB", ctype=ComponentType.DATABASE,
            replicas=2, encrypt_rest=True, encrypt_transit=True,
            auth=True, log=True, backup=False, failover=True,
            ids=True, segmented=True,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.HIPAA)
        backup_gaps = [gap for gap in report.gaps if "backup" in gap.finding.lower()]
        assert len(backup_gaps) >= 1


# ---------------------------------------------------------------------------
# PCI-DSS analysis tests
# ---------------------------------------------------------------------------


class TestPCIDSSAnalysis:
    def test_fully_compliant(self):
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(_fully_compliant_graph(), ComplianceFramework.PCI_DSS)
        assert report.framework == ComplianceFramework.PCI_DSS
        assert report.compliance_score == 100.0

    def test_missing_encryption_at_rest(self):
        g = InfraGraph()
        g.add_component(_comp(
            "db", "CDE DB", ctype=ComponentType.DATABASE,
            replicas=2, encrypt_rest=False, encrypt_transit=True,
            auth=True, log=True, ids=True, segmented=True,
            backup=True, failover=True,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.PCI_DSS)
        enc_gaps = [gap for gap in report.gaps if "encryption at rest" in gap.finding.lower()]
        assert len(enc_gaps) >= 1

    def test_missing_waf(self):
        g = InfraGraph()
        g.add_component(_comp(
            "web", "Web Server", ctype=ComponentType.WEB_SERVER,
            replicas=2, encrypt_rest=True, encrypt_transit=True,
            auth=True, log=True, ids=True, segmented=True,
            backup=True, failover=True, waf=False,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.PCI_DSS)
        waf_gaps = [gap for gap in report.gaps if "waf" in gap.finding.lower()]
        assert len(waf_gaps) >= 1

    def test_missing_ids(self):
        g = InfraGraph()
        g.add_component(_comp(
            "app", "App", replicas=2, encrypt_rest=True,
            encrypt_transit=True, auth=True, log=True,
            ids=False, waf=True, segmented=True, backup=True,
            failover=True,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.PCI_DSS)
        ids_gaps = [gap for gap in report.gaps if "ids" in gap.finding.lower()]
        assert len(ids_gaps) >= 1

    def test_missing_network_segmentation(self):
        g = InfraGraph()
        g.add_component(_comp(
            "app", "App", replicas=2, encrypt_rest=True,
            encrypt_transit=True, auth=True, log=True,
            ids=True, waf=True, segmented=False, backup=True,
            failover=True,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.PCI_DSS)
        seg_gaps = [gap for gap in report.gaps if "segmentation" in gap.finding.lower()]
        assert len(seg_gaps) >= 1


# ---------------------------------------------------------------------------
# GDPR analysis tests
# ---------------------------------------------------------------------------


class TestGDPRAnalysis:
    def test_fully_compliant(self):
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(_fully_compliant_graph(), ComplianceFramework.GDPR)
        assert report.framework == ComplianceFramework.GDPR
        assert report.compliance_score == 100.0

    def test_gdpr_encryption_at_rest(self):
        g = InfraGraph()
        g.add_component(_comp(
            "db", "User DB", ctype=ComponentType.DATABASE,
            replicas=2, encrypt_rest=False, encrypt_transit=True,
            auth=True, log=True, backup=True,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.GDPR)
        enc_gaps = [gap for gap in report.gaps if "encryption at rest" in gap.finding.lower()]
        assert len(enc_gaps) >= 1

    def test_gdpr_backup_restore(self):
        g = InfraGraph()
        g.add_component(_comp(
            "storage", "File Storage", ctype=ComponentType.STORAGE,
            replicas=2, encrypt_rest=True, encrypt_transit=True,
            auth=True, log=True, backup=False,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.GDPR)
        backup_gaps = [gap for gap in report.gaps if "backup" in gap.finding.lower()]
        assert len(backup_gaps) >= 1


# ---------------------------------------------------------------------------
# ISO27001 analysis tests
# ---------------------------------------------------------------------------


class TestISO27001Analysis:
    def test_fully_compliant(self):
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(_fully_compliant_graph(), ComplianceFramework.ISO27001)
        assert report.framework == ComplianceFramework.ISO27001
        assert report.compliance_score == 100.0

    def test_iso_failover_gap(self):
        g = InfraGraph()
        g.add_component(_comp(
            "db", "Database", ctype=ComponentType.DATABASE,
            replicas=2, encrypt_rest=True, encrypt_transit=True,
            auth=True, log=True, ids=True, segmented=True,
            backup=True, failover=False,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.ISO27001)
        fo_gaps = [gap for gap in report.gaps if "failover" in gap.finding.lower()]
        assert len(fo_gaps) >= 1

    def test_iso_network_segmentation(self):
        g = InfraGraph()
        g.add_component(_comp(
            "app", "App", replicas=2, encrypt_rest=True,
            encrypt_transit=True, auth=True, log=True,
            ids=True, segmented=False, backup=True, failover=True,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.ISO27001)
        seg_gaps = [gap for gap in report.gaps if "segmentation" in gap.finding.lower()]
        assert len(seg_gaps) >= 1


# ---------------------------------------------------------------------------
# Compliance score calculation
# ---------------------------------------------------------------------------


class TestComplianceScore:
    def test_perfect_score(self):
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(_fully_compliant_graph(), ComplianceFramework.SOC2)
        assert report.compliance_score == 100.0

    def test_zero_score_empty_graph(self):
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(InfraGraph(), ComplianceFramework.SOC2)
        assert report.compliance_score == 0.0

    def test_score_between_0_and_100(self):
        g = InfraGraph()
        # Partially compliant: some features enabled, some not
        g.add_component(_comp(
            "api", "API", replicas=2, encrypt_rest=True,
            encrypt_transit=True, auth=True, log=True,
            ids=True, waf=True, segmented=True, backup=True,
            failover=False,  # missing failover
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.SOC2)
        assert 0.0 < report.compliance_score < 100.0

    def test_score_decreases_with_more_gaps(self):
        analyzer = ComplianceGapAnalyzer()
        # Fully compliant
        report_good = analyzer.analyze(_fully_compliant_graph(), ComplianceFramework.SOC2)
        # Partially compliant
        report_bad = analyzer.analyze(_minimal_graph(), ComplianceFramework.SOC2)
        assert report_good.compliance_score > report_bad.compliance_score

    def test_compliant_plus_partial_plus_noncompliant_sum_to_total(self):
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(_minimal_graph(), ComplianceFramework.SOC2)
        assert (
            report.compliant_count + report.partial_count + report.non_compliant_count
            == report.total_requirements
        )


# ---------------------------------------------------------------------------
# Remediation priority ordering
# ---------------------------------------------------------------------------


class TestRemediationOrdering:
    def test_remediation_plan_ordered_by_priority(self):
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(_minimal_graph(), ComplianceFramework.SOC2)
        if len(report.remediation_plan) >= 2:
            # IMMEDIATE should come before HIGH which comes before MEDIUM
            priority_order = {"IMMEDIATE": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
            indices = []
            for item in report.remediation_plan:
                for pname, pidx in priority_order.items():
                    if item.startswith(f"[{pname}]"):
                        indices.append(pidx)
                        break
            # Should be non-decreasing
            assert indices == sorted(indices)

    def test_critical_gaps_are_immediate_or_high(self):
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(_minimal_graph(), ComplianceFramework.SOC2)
        for gap in report.critical_gaps:
            assert gap.priority in (RemediationPriority.IMMEDIATE, RemediationPriority.HIGH)

    def test_remediation_plan_not_empty_for_noncompliant(self):
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(_minimal_graph(), ComplianceFramework.SOC2)
        assert len(report.remediation_plan) > 0

    def test_remediation_plan_empty_for_fully_compliant(self):
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(_fully_compliant_graph(), ComplianceFramework.SOC2)
        assert len(report.remediation_plan) == 0


# ---------------------------------------------------------------------------
# analyze_all — multi-framework
# ---------------------------------------------------------------------------


class TestAnalyzeAll:
    def test_returns_all_five_frameworks(self):
        analyzer = ComplianceGapAnalyzer()
        results = analyzer.analyze_all(_minimal_graph())
        assert set(results.keys()) == set(ComplianceFramework)
        assert len(results) == 5

    def test_each_report_has_framework_set(self):
        analyzer = ComplianceGapAnalyzer()
        results = analyzer.analyze_all(_minimal_graph())
        for fw, report in results.items():
            assert report.framework == fw

    def test_each_report_has_requirements(self):
        analyzer = ComplianceGapAnalyzer()
        results = analyzer.analyze_all(_minimal_graph())
        for fw, report in results.items():
            assert report.total_requirements > 0, f"{fw} has no requirements"

    def test_all_frameworks_detect_gaps_on_minimal(self):
        analyzer = ComplianceGapAnalyzer()
        results = analyzer.analyze_all(_minimal_graph())
        for fw, report in results.items():
            assert report.non_compliant_count > 0, f"{fw} found no gaps on minimal graph"

    def test_all_frameworks_fully_compliant(self):
        analyzer = ComplianceGapAnalyzer()
        results = analyzer.analyze_all(_fully_compliant_graph())
        for fw, report in results.items():
            assert report.compliance_score == 100.0, f"{fw} is not fully compliant"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_graph(self):
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(InfraGraph(), ComplianceFramework.SOC2)
        assert report.total_requirements > 0
        assert report.compliance_score == 0.0
        assert report.non_compliant_count == report.total_requirements
        assert len(report.gaps) == report.total_requirements

    def test_empty_graph_all_frameworks(self):
        analyzer = ComplianceGapAnalyzer()
        results = analyzer.analyze_all(InfraGraph())
        for fw, report in results.items():
            assert report.compliance_score == 0.0, f"{fw} should be 0 for empty graph"

    def test_fully_compliant_has_no_gaps(self):
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(_fully_compliant_graph(), ComplianceFramework.HIPAA)
        assert len(report.gaps) == 0
        assert len(report.critical_gaps) == 0
        assert report.compliance_score == 100.0

    def test_fully_non_compliant(self):
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(_minimal_graph(), ComplianceFramework.SOC2)
        assert report.compliance_score < 100.0
        assert report.non_compliant_count > 0
        assert len(report.gaps) > 0

    def test_single_component_no_data_store(self):
        """Graph with only an app server — no data stores."""
        g = InfraGraph()
        g.add_component(_comp(
            "api", "API Only",
            replicas=3, encrypt_rest=True, encrypt_transit=True,
            auth=True, log=True, ids=True, waf=True,
            segmented=True, backup=True, failover=True,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.SOC2)
        # App server with all features — should have high compliance
        # (encryption at rest check skipped for non-data-stores,
        #  backup check skipped for non-data-stores)
        assert report.compliance_score >= 80.0

    def test_gap_references_correct_component(self):
        g = InfraGraph()
        g.add_component(_comp(
            "my-db", "My Special DB", ctype=ComponentType.DATABASE,
            encrypt_rest=False,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.SOC2)
        enc_gaps = [gap for gap in report.gaps if "encryption at rest" in gap.finding.lower()]
        assert any(gap.component_id == "my-db" for gap in enc_gaps)
        assert any(gap.component_name == "My Special DB" for gap in enc_gaps)

    def test_multiple_components_with_mixed_compliance(self):
        """One compliant component and one non-compliant."""
        g = InfraGraph()
        g.add_component(_comp(
            "db1", "Encrypted DB", ctype=ComponentType.DATABASE,
            replicas=2, encrypt_rest=True, encrypt_transit=True,
            auth=True, log=True, ids=True, segmented=True,
            backup=True, failover=True,
        ))
        g.add_component(_comp(
            "db2", "Unencrypted DB", ctype=ComponentType.DATABASE,
            replicas=1, encrypt_rest=False, encrypt_transit=False,
            auth=False, log=False,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.SOC2)
        # Should detect gaps for db2 but not db1
        db2_gaps = [gap for gap in report.gaps if gap.component_id == "db2"]
        db1_gaps = [gap for gap in report.gaps if gap.component_id == "db1"]
        assert len(db2_gaps) > 0
        assert len(db1_gaps) == 0
        # Score is below 100 because db2 is non-compliant
        assert report.compliance_score < 100.0

    def test_storage_type_checked_for_backup(self):
        """Storage components should be checked for backup."""
        g = InfraGraph()
        g.add_component(_comp(
            "s3", "Object Storage", ctype=ComponentType.STORAGE,
            replicas=2, encrypt_rest=True, encrypt_transit=True,
            auth=True, log=True, ids=True, segmented=True,
            backup=False, failover=True,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.SOC2)
        backup_gaps = [gap for gap in report.gaps if "backup" in gap.finding.lower()]
        assert len(backup_gaps) >= 1

    def test_cache_type_checked_for_encryption(self):
        """Cache components should be checked for encryption at rest."""
        g = InfraGraph()
        g.add_component(_comp(
            "redis", "Redis Cache", ctype=ComponentType.CACHE,
            replicas=2, encrypt_rest=False, encrypt_transit=True,
            auth=True, log=True, ids=True, segmented=True,
            backup=True, failover=True,
        ))
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(g, ComplianceFramework.SOC2)
        enc_gaps = [gap for gap in report.gaps if "encryption at rest" in gap.finding.lower()]
        assert len(enc_gaps) >= 1

    def test_remediation_plan_deduplicates(self):
        """If multiple components have the same remediation, it should not be duplicated."""
        analyzer = ComplianceGapAnalyzer()
        report = analyzer.analyze(_minimal_graph(), ComplianceFramework.SOC2)
        # Check no exact duplicates in remediation_plan
        assert len(report.remediation_plan) == len(set(report.remediation_plan))
