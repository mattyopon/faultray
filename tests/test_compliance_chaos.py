"""Tests for the Compliance-Driven Chaos Generator module."""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType, HealthStatus, SecurityProfile
from faultray.model.graph import InfraGraph
from faultray.simulator.compliance_chaos import (
    ComplianceChaosExperiment,
    ComplianceChaosGenerator,
    ComplianceChaosReport,
    ComplianceControl,
    ComplianceFramework,
    ComplianceGap,
    ControlCategory,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
) -> Component:
    return Component(id=cid, name=name, type=ctype, replicas=replicas)


def _secure_comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.DATABASE,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=3)
    c.security = SecurityProfile(
        encryption_at_rest=True,
        encryption_in_transit=True,
        waf_protected=True,
        rate_limiting=True,
        auth_required=True,
        network_segmented=True,
        backup_enabled=True,
        log_enabled=True,
        ids_monitored=True,
    )
    return c


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


# ======================================================================
# 1. Enum value tests
# ======================================================================


class TestEnumValues:
    """Verify enum members and their string values."""

    def test_compliance_framework_members(self):
        assert set(ComplianceFramework) == {
            ComplianceFramework.SOC2,
            ComplianceFramework.HIPAA,
            ComplianceFramework.PCI_DSS,
            ComplianceFramework.ISO27001,
            ComplianceFramework.GDPR,
        }

    def test_compliance_framework_values(self):
        assert ComplianceFramework.SOC2.value == "soc2"
        assert ComplianceFramework.HIPAA.value == "hipaa"
        assert ComplianceFramework.PCI_DSS.value == "pci_dss"
        assert ComplianceFramework.ISO27001.value == "iso27001"
        assert ComplianceFramework.GDPR.value == "gdpr"

    def test_control_category_members(self):
        assert len(ControlCategory) == 8

    def test_control_category_values(self):
        assert ControlCategory.DATA_PROTECTION.value == "data_protection"
        assert ControlCategory.ACCESS_CONTROL.value == "access_control"
        assert ControlCategory.AVAILABILITY.value == "availability"
        assert ControlCategory.AUDIT_LOGGING.value == "audit_logging"
        assert ControlCategory.ENCRYPTION.value == "encryption"
        assert ControlCategory.BACKUP_RECOVERY.value == "backup_recovery"
        assert ControlCategory.INCIDENT_RESPONSE.value == "incident_response"
        assert ControlCategory.NETWORK_SECURITY.value == "network_security"

    def test_framework_is_str_enum(self):
        assert isinstance(ComplianceFramework.SOC2, str)

    def test_category_is_str_enum(self):
        assert isinstance(ControlCategory.ENCRYPTION, str)


# ======================================================================
# 2. Empty graph (each framework)
# ======================================================================


class TestEmptyGraph:
    """Tests with an empty InfraGraph — no components at all."""

    @pytest.fixture()
    def gen(self):
        return ComplianceChaosGenerator(_graph())

    @pytest.mark.parametrize("fw", list(ComplianceFramework))
    def test_empty_graph_no_experiments(self, gen, fw):
        report = gen.generate(fw)
        assert report.experiments_generated == 0

    @pytest.mark.parametrize("fw", list(ComplianceFramework))
    def test_empty_graph_no_gaps(self, gen, fw):
        report = gen.generate(fw)
        assert report.gaps_found == 0

    @pytest.mark.parametrize("fw", list(ComplianceFramework))
    def test_empty_graph_coverage_0(self, gen, fw):
        report = gen.generate(fw)
        # No components means no experiments, so 0 controls covered out of N
        assert report.coverage_percentage == 0.0

    @pytest.mark.parametrize("fw", list(ComplianceFramework))
    def test_empty_graph_framework_matches(self, gen, fw):
        report = gen.generate(fw)
        assert report.framework == fw

    def test_empty_graph_generate_all(self, gen):
        reports = gen.generate_all()
        assert len(reports) == 5
        for r in reports:
            assert r.experiments_generated == 0


# ======================================================================
# 3. Control definitions per framework
# ======================================================================


class TestControlDefinitions:
    """Verify built-in control definitions."""

    @pytest.fixture()
    def gen(self):
        return ComplianceChaosGenerator(_graph())

    def test_soc2_has_6_controls(self, gen):
        controls = gen._get_controls(ComplianceFramework.SOC2)
        assert len(controls) == 6

    def test_hipaa_has_5_controls(self, gen):
        controls = gen._get_controls(ComplianceFramework.HIPAA)
        assert len(controls) == 5

    def test_pci_dss_has_5_controls(self, gen):
        controls = gen._get_controls(ComplianceFramework.PCI_DSS)
        assert len(controls) == 5

    def test_iso27001_has_4_controls(self, gen):
        controls = gen._get_controls(ComplianceFramework.ISO27001)
        assert len(controls) == 4

    def test_gdpr_has_4_controls(self, gen):
        controls = gen._get_controls(ComplianceFramework.GDPR)
        assert len(controls) == 4

    def test_soc2_control_ids(self, gen):
        ids = {c.control_id for c in gen._get_controls(ComplianceFramework.SOC2)}
        assert ids == {"CC6.1", "A1.2", "CC6.7", "CC7.2", "A1.3", "CC7.4"}

    def test_hipaa_control_ids(self, gen):
        ids = {c.control_id for c in gen._get_controls(ComplianceFramework.HIPAA)}
        assert ids == {
            "164.312(a)",
            "164.312(e)",
            "164.312(b)",
            "164.308(a)(7)",
            "164.308(a)(7)(ii)(B)",
        }

    def test_pci_dss_control_ids(self, gen):
        ids = {c.control_id for c in gen._get_controls(ComplianceFramework.PCI_DSS)}
        assert ids == {"Req 1", "Req 4", "Req 7", "Req 10", "Req 12.10"}

    def test_iso27001_control_ids(self, gen):
        ids = {c.control_id for c in gen._get_controls(ComplianceFramework.ISO27001)}
        assert ids == {"A.9", "A.10", "A.17", "A.12.3"}

    def test_gdpr_control_ids(self, gen):
        ids = {c.control_id for c in gen._get_controls(ComplianceFramework.GDPR)}
        assert ids == {"Art.32", "Art.32(1)(a)", "Art.32(1)(b)", "Art.32(1)(c)"}

    def test_all_controls_chaos_relevant(self, gen):
        for fw in ComplianceFramework:
            for c in gen._get_controls(fw):
                assert c.chaos_relevant is True

    def test_soc2_categories(self, gen):
        cats = {c.category for c in gen._get_controls(ComplianceFramework.SOC2)}
        assert ControlCategory.DATA_PROTECTION in cats
        assert ControlCategory.AVAILABILITY in cats
        assert ControlCategory.ENCRYPTION in cats
        assert ControlCategory.AUDIT_LOGGING in cats
        assert ControlCategory.BACKUP_RECOVERY in cats
        assert ControlCategory.INCIDENT_RESPONSE in cats

    def test_pci_dss_has_network_security(self, gen):
        cats = {c.category for c in gen._get_controls(ComplianceFramework.PCI_DSS)}
        assert ControlCategory.NETWORK_SECURITY in cats

    def test_controls_return_copies(self, gen):
        """_get_controls should return a new list each time."""
        a = gen._get_controls(ComplianceFramework.SOC2)
        b = gen._get_controls(ComplianceFramework.SOC2)
        assert a is not b
        assert a == b


# ======================================================================
# 4. Experiment generation per control category
# ======================================================================


class TestExperimentGeneration:
    """Verify experiments are generated for the correct component configurations."""

    # --- DATA_PROTECTION ---

    def test_data_protection_db_no_encryption(self):
        db = _comp("db1", "MainDB", ComponentType.DATABASE)
        gen = ComplianceChaosGenerator(_graph(db))
        report = gen.generate(ComplianceFramework.SOC2)
        dp_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.DATA_PROTECTION
        ]
        assert len(dp_exps) >= 1
        assert "unauthorized access" in dp_exps[0].experiment_description.lower()

    def test_data_protection_storage_no_encryption(self):
        st = _comp("s1", "BlobStore", ComponentType.STORAGE)
        gen = ComplianceChaosGenerator(_graph(st))
        report = gen.generate(ComplianceFramework.HIPAA)
        dp_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.DATA_PROTECTION
        ]
        assert len(dp_exps) >= 1

    def test_data_protection_cache_no_encryption(self):
        c = _comp("c1", "Redis", ComponentType.CACHE)
        gen = ComplianceChaosGenerator(_graph(c))
        report = gen.generate(ComplianceFramework.GDPR)
        dp_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.DATA_PROTECTION
        ]
        assert len(dp_exps) >= 1

    def test_data_protection_app_server_skipped(self):
        app = _comp("a1", "AppServer", ComponentType.APP_SERVER)
        gen = ComplianceChaosGenerator(_graph(app))
        report = gen.generate(ComplianceFramework.SOC2)
        dp_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.DATA_PROTECTION
        ]
        assert len(dp_exps) == 0

    def test_data_protection_encrypted_db_skipped(self):
        db = _secure_comp("db1", "SecureDB")
        gen = ComplianceChaosGenerator(_graph(db))
        report = gen.generate(ComplianceFramework.SOC2)
        dp_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.DATA_PROTECTION
        ]
        assert len(dp_exps) == 0

    # --- AVAILABILITY ---

    def test_availability_single_replica(self):
        app = _comp("a1", "App", replicas=1)
        gen = ComplianceChaosGenerator(_graph(app))
        report = gen.generate(ComplianceFramework.SOC2)
        avail_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.AVAILABILITY
        ]
        assert len(avail_exps) >= 1
        assert "kill single instance" in avail_exps[0].experiment_description.lower()

    def test_availability_multi_replica_skipped(self):
        app = _comp("a1", "App", replicas=3)
        gen = ComplianceChaosGenerator(_graph(app))
        report = gen.generate(ComplianceFramework.SOC2)
        avail_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.AVAILABILITY
        ]
        assert len(avail_exps) == 0

    # --- ENCRYPTION ---

    def test_encryption_no_transit_encryption(self):
        app = _comp("a1", "App")
        gen = ComplianceChaosGenerator(_graph(app))
        report = gen.generate(ComplianceFramework.SOC2)
        enc_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.ENCRYPTION
        ]
        assert len(enc_exps) >= 1
        assert "data exposure" in enc_exps[0].experiment_description.lower()

    def test_encryption_with_transit_encryption_skipped(self):
        app = _comp("a1", "App")
        app.security.encryption_in_transit = True
        gen = ComplianceChaosGenerator(_graph(app))
        report = gen.generate(ComplianceFramework.SOC2)
        enc_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.ENCRYPTION
        ]
        assert len(enc_exps) == 0

    # --- AUDIT_LOGGING ---

    def test_audit_logging_disabled(self):
        app = _comp("a1", "App")
        gen = ComplianceChaosGenerator(_graph(app))
        report = gen.generate(ComplianceFramework.SOC2)
        log_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.AUDIT_LOGGING
        ]
        assert len(log_exps) >= 1
        assert "audit trail" in log_exps[0].experiment_description.lower()

    def test_audit_logging_enabled_skipped(self):
        app = _comp("a1", "App")
        app.security.log_enabled = True
        gen = ComplianceChaosGenerator(_graph(app))
        report = gen.generate(ComplianceFramework.SOC2)
        log_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.AUDIT_LOGGING
        ]
        assert len(log_exps) == 0

    # --- BACKUP_RECOVERY ---

    def test_backup_recovery_db_no_backup(self):
        db = _comp("db1", "DB", ComponentType.DATABASE)
        gen = ComplianceChaosGenerator(_graph(db))
        report = gen.generate(ComplianceFramework.SOC2)
        br_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.BACKUP_RECOVERY
        ]
        assert len(br_exps) >= 1
        assert "data loss" in br_exps[0].experiment_description.lower()

    def test_backup_recovery_storage_no_backup(self):
        st = _comp("s1", "Storage", ComponentType.STORAGE)
        gen = ComplianceChaosGenerator(_graph(st))
        report = gen.generate(ComplianceFramework.HIPAA)
        br_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.BACKUP_RECOVERY
        ]
        assert len(br_exps) >= 1

    def test_backup_recovery_cache_no_backup(self):
        c = _comp("c1", "Cache", ComponentType.CACHE)
        gen = ComplianceChaosGenerator(_graph(c))
        report = gen.generate(ComplianceFramework.ISO27001)
        br_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.BACKUP_RECOVERY
        ]
        assert len(br_exps) >= 1

    def test_backup_recovery_app_server_skipped(self):
        app = _comp("a1", "App", ComponentType.APP_SERVER)
        gen = ComplianceChaosGenerator(_graph(app))
        report = gen.generate(ComplianceFramework.SOC2)
        br_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.BACKUP_RECOVERY
        ]
        assert len(br_exps) == 0

    def test_backup_recovery_with_backup_skipped(self):
        db = _comp("db1", "DB", ComponentType.DATABASE)
        db.security.backup_enabled = True
        gen = ComplianceChaosGenerator(_graph(db))
        report = gen.generate(ComplianceFramework.SOC2)
        br_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.BACKUP_RECOVERY
        ]
        assert len(br_exps) == 0

    # --- INCIDENT_RESPONSE ---

    def test_incident_response_all_components(self):
        a = _comp("a1", "App1")
        b = _comp("a2", "App2")
        gen = ComplianceChaosGenerator(_graph(a, b))
        report = gen.generate(ComplianceFramework.SOC2)
        ir_exps = [
            e
            for e in report.experiments
            if e.control.category == ControlCategory.INCIDENT_RESPONSE
        ]
        assert len(ir_exps) == 2
        assert "cascade failure" in ir_exps[0].experiment_description.lower()

    # --- NETWORK_SECURITY ---

    def test_network_security_web_server_no_waf(self):
        ws = _comp("ws1", "WebServer", ComponentType.WEB_SERVER)
        gen = ComplianceChaosGenerator(_graph(ws))
        report = gen.generate(ComplianceFramework.PCI_DSS)
        ns_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.NETWORK_SECURITY
        ]
        assert len(ns_exps) >= 1
        assert "ddos" in ns_exps[0].experiment_description.lower()

    def test_network_security_non_web_server_skipped(self):
        app = _comp("a1", "App", ComponentType.APP_SERVER)
        gen = ComplianceChaosGenerator(_graph(app))
        report = gen.generate(ComplianceFramework.PCI_DSS)
        ns_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.NETWORK_SECURITY
        ]
        assert len(ns_exps) == 0

    def test_network_security_web_server_with_waf_skipped(self):
        ws = _comp("ws1", "WebServer", ComponentType.WEB_SERVER)
        ws.security.waf_protected = True
        gen = ComplianceChaosGenerator(_graph(ws))
        report = gen.generate(ComplianceFramework.PCI_DSS)
        ns_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.NETWORK_SECURITY
        ]
        assert len(ns_exps) == 0

    # --- ACCESS_CONTROL ---

    def test_access_control_no_auth(self):
        app = _comp("a1", "App")
        gen = ComplianceChaosGenerator(_graph(app))
        report = gen.generate(ComplianceFramework.PCI_DSS)
        ac_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.ACCESS_CONTROL
        ]
        assert len(ac_exps) >= 1
        assert "access during partial outage" in ac_exps[0].experiment_description.lower()

    def test_access_control_with_auth_skipped(self):
        app = _comp("a1", "App")
        app.security.auth_required = True
        gen = ComplianceChaosGenerator(_graph(app))
        report = gen.generate(ComplianceFramework.PCI_DSS)
        ac_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.ACCESS_CONTROL
        ]
        assert len(ac_exps) == 0


# ======================================================================
# 5. Gap detection (each gap type)
# ======================================================================


class TestGapDetection:
    """Verify compliance gaps are detected properly."""

    def test_gap_missing_encryption_at_rest(self):
        db = _comp("db1", "DB", ComponentType.DATABASE)
        gen = ComplianceChaosGenerator(_graph(db))
        report = gen.generate(ComplianceFramework.SOC2)
        dp_gaps = [g for g in report.gaps if g.control.category == ControlCategory.DATA_PROTECTION]
        assert len(dp_gaps) >= 1
        assert "encryption at rest" in dp_gaps[0].gap_description.lower()

    def test_gap_missing_encryption_at_rest_storage(self):
        st = _comp("s1", "Store", ComponentType.STORAGE)
        gen = ComplianceChaosGenerator(_graph(st))
        report = gen.generate(ComplianceFramework.GDPR)
        dp_gaps = [g for g in report.gaps if g.control.category == ControlCategory.DATA_PROTECTION]
        assert len(dp_gaps) >= 1

    def test_gap_no_backup_on_data_components(self):
        db = _comp("db1", "DB", ComponentType.DATABASE)
        gen = ComplianceChaosGenerator(_graph(db))
        report = gen.generate(ComplianceFramework.HIPAA)
        br_gaps = [g for g in report.gaps if g.control.category == ControlCategory.BACKUP_RECOVERY]
        assert len(br_gaps) >= 1
        assert "backup" in br_gaps[0].gap_description.lower()

    def test_gap_no_logging(self):
        app = _comp("a1", "App")
        gen = ComplianceChaosGenerator(_graph(app))
        report = gen.generate(ComplianceFramework.SOC2)
        log_gaps = [g for g in report.gaps if g.control.category == ControlCategory.AUDIT_LOGGING]
        assert len(log_gaps) >= 1
        assert "logging disabled" in log_gaps[0].gap_description.lower()

    def test_gap_no_waf_on_web_server(self):
        ws = _comp("ws1", "WebServer", ComponentType.WEB_SERVER)
        gen = ComplianceChaosGenerator(_graph(ws))
        report = gen.generate(ComplianceFramework.PCI_DSS)
        ns_gaps = [
            g for g in report.gaps if g.control.category == ControlCategory.NETWORK_SECURITY
        ]
        assert len(ns_gaps) >= 1
        assert "waf" in ns_gaps[0].gap_description.lower()

    def test_gap_single_replica_no_failover(self):
        app = _comp("a1", "App", replicas=1)
        gen = ComplianceChaosGenerator(_graph(app))
        report = gen.generate(ComplianceFramework.SOC2)
        avail_gaps = [g for g in report.gaps if g.control.category == ControlCategory.AVAILABILITY]
        assert len(avail_gaps) >= 1
        assert "single replica" in avail_gaps[0].gap_description.lower()

    def test_gap_single_replica_with_failover_no_gap(self):
        from faultray.model.components import FailoverConfig

        app = _comp("a1", "App", replicas=1)
        app.failover = FailoverConfig(enabled=True)
        gen = ComplianceChaosGenerator(_graph(app))
        report = gen.generate(ComplianceFramework.SOC2)
        avail_gaps = [g for g in report.gaps if g.control.category == ControlCategory.AVAILABILITY]
        assert len(avail_gaps) == 0

    def test_gap_no_auth_required(self):
        app = _comp("a1", "App")
        gen = ComplianceChaosGenerator(_graph(app))
        report = gen.generate(ComplianceFramework.PCI_DSS)
        ac_gaps = [g for g in report.gaps if g.control.category == ControlCategory.ACCESS_CONTROL]
        assert len(ac_gaps) >= 1
        assert "authentication" in ac_gaps[0].gap_description.lower()

    def test_gap_missing_encryption_in_transit(self):
        app = _comp("a1", "App")
        gen = ComplianceChaosGenerator(_graph(app))
        report = gen.generate(ComplianceFramework.SOC2)
        enc_gaps = [g for g in report.gaps if g.control.category == ControlCategory.ENCRYPTION]
        assert len(enc_gaps) >= 1
        assert "encryption in transit" in enc_gaps[0].gap_description.lower()

    def test_gap_remediation_present(self):
        db = _comp("db1", "DB", ComponentType.DATABASE)
        gen = ComplianceChaosGenerator(_graph(db))
        report = gen.generate(ComplianceFramework.SOC2)
        for gap in report.gaps:
            assert gap.remediation, f"Gap {gap.gap_description} has no remediation"

    def test_gap_component_ids_match(self):
        db = _comp("db1", "MainDB", ComponentType.DATABASE)
        gen = ComplianceChaosGenerator(_graph(db))
        report = gen.generate(ComplianceFramework.SOC2)
        for gap in report.gaps:
            assert gap.component_id == "db1"
            assert gap.component_name == "MainDB"


# ======================================================================
# 6. Fully secure component (no gaps)
# ======================================================================


class TestFullySecureComponent:
    """A fully secured component should produce no gaps."""

    def test_no_gaps_secure_db(self):
        db = _secure_comp("db1", "SecureDB")
        gen = ComplianceChaosGenerator(_graph(db))
        for fw in ComplianceFramework:
            report = gen.generate(fw)
            # Data protection, encryption, backup, logging gaps should be zero
            relevant_gaps = [
                g
                for g in report.gaps
                if g.component_id == "db1"
                and g.control.category
                in {
                    ControlCategory.DATA_PROTECTION,
                    ControlCategory.ENCRYPTION,
                    ControlCategory.BACKUP_RECOVERY,
                    ControlCategory.AUDIT_LOGGING,
                    ControlCategory.ACCESS_CONTROL,
                }
            ]
            assert relevant_gaps == [], f"Unexpected gaps for {fw}: {relevant_gaps}"

    def test_no_availability_gap_multi_replica(self):
        db = _secure_comp("db1", "SecureDB")
        gen = ComplianceChaosGenerator(_graph(db))
        report = gen.generate(ComplianceFramework.SOC2)
        avail_gaps = [g for g in report.gaps if g.control.category == ControlCategory.AVAILABILITY]
        assert len(avail_gaps) == 0

    def test_secure_web_server_no_waf_gap(self):
        ws = _secure_comp("ws1", "SecureWeb", ComponentType.WEB_SERVER)
        gen = ComplianceChaosGenerator(_graph(ws))
        report = gen.generate(ComplianceFramework.PCI_DSS)
        ns_gaps = [
            g for g in report.gaps if g.control.category == ControlCategory.NETWORK_SECURITY
        ]
        assert len(ns_gaps) == 0


# ======================================================================
# 7. generate_all() returning 5 reports
# ======================================================================


class TestGenerateAll:
    """Test generate_all() across all frameworks."""

    def test_generate_all_returns_5_reports(self):
        gen = ComplianceChaosGenerator(_graph(_comp("a1", "App")))
        reports = gen.generate_all()
        assert len(reports) == 5

    def test_generate_all_frameworks_present(self):
        gen = ComplianceChaosGenerator(_graph(_comp("a1", "App")))
        reports = gen.generate_all()
        frameworks = {r.framework for r in reports}
        assert frameworks == set(ComplianceFramework)

    def test_generate_all_returns_list(self):
        gen = ComplianceChaosGenerator(_graph())
        reports = gen.generate_all()
        assert isinstance(reports, list)
        for r in reports:
            assert isinstance(r, ComplianceChaosReport)

    def test_generate_all_each_has_correct_total_controls(self):
        gen = ComplianceChaosGenerator(_graph(_comp("a1", "App")))
        reports = gen.generate_all()
        expected = {
            ComplianceFramework.SOC2: 6,
            ComplianceFramework.HIPAA: 5,
            ComplianceFramework.PCI_DSS: 5,
            ComplianceFramework.ISO27001: 4,
            ComplianceFramework.GDPR: 4,
        }
        for r in reports:
            assert r.total_controls == expected[r.framework]


# ======================================================================
# 8. Coverage percentage calculation
# ======================================================================


class TestCoveragePercentage:
    """Test that coverage percentage is calculated correctly."""

    def test_coverage_0_empty_graph(self):
        gen = ComplianceChaosGenerator(_graph())
        report = gen.generate(ComplianceFramework.SOC2)
        assert report.coverage_percentage == 0.0

    def test_coverage_with_insecure_component(self):
        """An insecure component should produce experiments covering multiple controls."""
        db = _comp("db1", "DB", ComponentType.DATABASE)
        gen = ComplianceChaosGenerator(_graph(db))
        report = gen.generate(ComplianceFramework.SOC2)
        assert report.coverage_percentage > 0.0
        assert report.coverage_percentage <= 100.0

    def test_coverage_percentage_is_rounded(self):
        gen = ComplianceChaosGenerator(_graph(_comp("a1", "App")))
        report = gen.generate(ComplianceFramework.SOC2)
        # Check it is rounded to 1 decimal
        assert report.coverage_percentage == round(report.coverage_percentage, 1)

    def test_full_coverage_all_control_types_present(self):
        """Create components that trigger experiments for all SOC2 control categories."""
        db = _comp("db1", "DB", ComponentType.DATABASE)  # DATA_PROTECTION, BACKUP_RECOVERY
        app = _comp("a1", "App")  # AVAILABILITY, ENCRYPTION, AUDIT_LOGGING, INCIDENT_RESPONSE
        gen = ComplianceChaosGenerator(_graph(db, app))
        report = gen.generate(ComplianceFramework.SOC2)
        assert report.coverage_percentage == 100.0


# ======================================================================
# 9. Summary text
# ======================================================================


class TestSummaryText:
    """Verify the report summary string content."""

    def test_summary_contains_framework_name(self):
        gen = ComplianceChaosGenerator(_graph(_comp("a1", "App")))
        report = gen.generate(ComplianceFramework.SOC2)
        assert "SOC2" in report.summary

    def test_summary_contains_experiment_count(self):
        gen = ComplianceChaosGenerator(_graph(_comp("a1", "App")))
        report = gen.generate(ComplianceFramework.SOC2)
        assert str(report.experiments_generated) in report.summary

    def test_summary_contains_gap_count(self):
        gen = ComplianceChaosGenerator(_graph(_comp("a1", "App")))
        report = gen.generate(ComplianceFramework.SOC2)
        assert str(report.gaps_found) in report.summary

    def test_summary_contains_coverage(self):
        gen = ComplianceChaosGenerator(_graph(_comp("a1", "App")))
        report = gen.generate(ComplianceFramework.SOC2)
        assert "Coverage" in report.summary

    def test_summary_contains_chaos_relevant_count(self):
        gen = ComplianceChaosGenerator(_graph(_comp("a1", "App")))
        report = gen.generate(ComplianceFramework.SOC2)
        assert "chaos-relevant" in report.summary.lower()


# ======================================================================
# 10. Mixed components (some secure, some insecure)
# ======================================================================


class TestMixedComponents:
    """Mix of secure and insecure components."""

    def test_mixed_generates_experiments_for_insecure_only(self):
        secure_db = _secure_comp("db_s", "SecureDB")
        insecure_db = _comp("db_i", "InsecureDB", ComponentType.DATABASE)
        gen = ComplianceChaosGenerator(_graph(secure_db, insecure_db))
        report = gen.generate(ComplianceFramework.SOC2)

        dp_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.DATA_PROTECTION
        ]
        target_ids = [t for e in dp_exps for t in e.target_components]
        assert "db_i" in target_ids
        assert "db_s" not in target_ids

    def test_mixed_gaps_only_for_insecure(self):
        secure_db = _secure_comp("db_s", "SecureDB")
        insecure_db = _comp("db_i", "InsecureDB", ComponentType.DATABASE)
        gen = ComplianceChaosGenerator(_graph(secure_db, insecure_db))
        report = gen.generate(ComplianceFramework.SOC2)

        dp_gaps = [g for g in report.gaps if g.control.category == ControlCategory.DATA_PROTECTION]
        gap_ids = [g.component_id for g in dp_gaps]
        assert "db_i" in gap_ids
        assert "db_s" not in gap_ids

    def test_mixed_report_counts(self):
        secure = _secure_comp("s1", "SecureApp", ComponentType.APP_SERVER)
        insecure = _comp("i1", "InsecureApp")
        gen = ComplianceChaosGenerator(_graph(secure, insecure))
        report = gen.generate(ComplianceFramework.SOC2)
        assert report.experiments_generated > 0
        assert report.gaps_found > 0

    def test_mixed_web_servers(self):
        """One WAF-protected web server, one not."""
        ws_secure = _comp("ws_s", "SecureWeb", ComponentType.WEB_SERVER)
        ws_secure.security.waf_protected = True
        ws_insecure = _comp("ws_i", "InsecureWeb", ComponentType.WEB_SERVER)
        gen = ComplianceChaosGenerator(_graph(ws_secure, ws_insecure))
        report = gen.generate(ComplianceFramework.PCI_DSS)

        ns_gaps = [
            g for g in report.gaps if g.control.category == ControlCategory.NETWORK_SECURITY
        ]
        gap_ids = [g.component_id for g in ns_gaps]
        assert "ws_i" in gap_ids
        assert "ws_s" not in gap_ids


# ======================================================================
# 11. Edge cases
# ======================================================================


class TestEdgeCases:
    """Edge cases: all compliant, all failing, single component."""

    def test_all_components_fully_compliant(self):
        """When all components are fully secured, no gaps or experiments for security controls."""
        comps = [
            _secure_comp("db1", "DB1", ComponentType.DATABASE),
            _secure_comp("ws1", "Web1", ComponentType.WEB_SERVER),
            _secure_comp("app1", "App1", ComponentType.APP_SERVER),
        ]
        gen = ComplianceChaosGenerator(_graph(*comps))
        report = gen.generate(ComplianceFramework.SOC2)
        # Should have 0 data_protection / encryption / backup / logging / access control gaps
        non_avail_gaps = [
            g for g in report.gaps if g.control.category != ControlCategory.AVAILABILITY
        ]
        # Secured components have replicas=3, so availability gaps also zero
        assert report.gaps_found == 0
        assert non_avail_gaps == []

    def test_all_components_failing_every_control(self):
        """Insecure single-replica DB + web server should generate max experiments/gaps."""
        db = _comp("db1", "DB", ComponentType.DATABASE)
        ws = _comp("ws1", "Web", ComponentType.WEB_SERVER)
        gen = ComplianceChaosGenerator(_graph(db, ws))

        for fw in ComplianceFramework:
            report = gen.generate(fw)
            assert report.experiments_generated > 0
            assert report.gaps_found > 0

    def test_single_component_db(self):
        db = _comp("db1", "SingleDB", ComponentType.DATABASE)
        gen = ComplianceChaosGenerator(_graph(db))
        report = gen.generate(ComplianceFramework.SOC2)
        assert report.total_controls == 6
        assert report.chaos_relevant_controls == 6
        assert report.experiments_generated > 0
        assert report.gaps_found > 0

    def test_single_component_app(self):
        app = _comp("a1", "SingleApp", ComponentType.APP_SERVER)
        gen = ComplianceChaosGenerator(_graph(app))
        report = gen.generate(ComplianceFramework.HIPAA)
        assert report.total_controls == 5
        assert report.experiments_generated > 0

    def test_experiment_severity_values(self):
        db = _comp("db1", "DB", ComponentType.DATABASE)
        ws = _comp("ws1", "Web", ComponentType.WEB_SERVER)
        gen = ComplianceChaosGenerator(_graph(db, ws))
        report = gen.generate(ComplianceFramework.SOC2)
        valid_severities = {"critical", "high", "medium", "low"}
        for exp in report.experiments:
            assert exp.severity_if_failed in valid_severities

    def test_experiment_target_components_non_empty(self):
        app = _comp("a1", "App")
        gen = ComplianceChaosGenerator(_graph(app))
        report = gen.generate(ComplianceFramework.SOC2)
        for exp in report.experiments:
            assert len(exp.target_components) >= 1

    def test_experiment_fields_non_empty(self):
        app = _comp("a1", "App")
        gen = ComplianceChaosGenerator(_graph(app))
        report = gen.generate(ComplianceFramework.SOC2)
        for exp in report.experiments:
            assert exp.experiment_description
            assert exp.validation_criteria
            assert exp.expected_behavior
            assert exp.failure_scenario

    def test_gap_fields_non_empty(self):
        db = _comp("db1", "DB", ComponentType.DATABASE)
        gen = ComplianceChaosGenerator(_graph(db))
        report = gen.generate(ComplianceFramework.SOC2)
        for gap in report.gaps:
            assert gap.component_id
            assert gap.component_name
            assert gap.gap_description
            assert gap.remediation

    def test_report_experiments_generated_matches_list_length(self):
        app = _comp("a1", "App")
        gen = ComplianceChaosGenerator(_graph(app))
        report = gen.generate(ComplianceFramework.SOC2)
        assert report.experiments_generated == len(report.experiments)

    def test_report_gaps_found_matches_list_length(self):
        db = _comp("db1", "DB", ComponentType.DATABASE)
        gen = ComplianceChaosGenerator(_graph(db))
        report = gen.generate(ComplianceFramework.SOC2)
        assert report.gaps_found == len(report.gaps)


# ======================================================================
# 12. Additional coverage tests (dataclass construction, edge cases)
# ======================================================================


class TestDataclassConstruction:
    """Test direct construction of dataclasses."""

    def test_compliance_control_fields(self):
        ctrl = ComplianceControl(
            framework=ComplianceFramework.SOC2,
            category=ControlCategory.ENCRYPTION,
            control_id="TEST-1",
            description="Test control",
            chaos_relevant=False,
        )
        assert ctrl.framework == ComplianceFramework.SOC2
        assert ctrl.category == ControlCategory.ENCRYPTION
        assert ctrl.control_id == "TEST-1"
        assert ctrl.description == "Test control"
        assert ctrl.chaos_relevant is False

    def test_compliance_chaos_experiment_fields(self):
        ctrl = ComplianceControl(
            framework=ComplianceFramework.HIPAA,
            category=ControlCategory.DATA_PROTECTION,
            control_id="X",
            description="desc",
            chaos_relevant=True,
        )
        exp = ComplianceChaosExperiment(
            control=ctrl,
            experiment_description="Test experiment",
            target_components=["c1", "c2"],
            validation_criteria="criteria",
            expected_behavior="behavior",
            failure_scenario="scenario",
            severity_if_failed="medium",
        )
        assert exp.control is ctrl
        assert exp.target_components == ["c1", "c2"]
        assert exp.severity_if_failed == "medium"

    def test_compliance_gap_fields(self):
        ctrl = ComplianceControl(
            framework=ComplianceFramework.GDPR,
            category=ControlCategory.AVAILABILITY,
            control_id="Y",
            description="desc",
            chaos_relevant=True,
        )
        gap = ComplianceGap(
            control=ctrl,
            component_id="comp-1",
            component_name="MyComp",
            gap_description="Missing something",
            remediation="Fix it",
        )
        assert gap.component_id == "comp-1"
        assert gap.component_name == "MyComp"

    def test_compliance_chaos_report_fields(self):
        report = ComplianceChaosReport(
            framework=ComplianceFramework.ISO27001,
            total_controls=4,
            chaos_relevant_controls=4,
            experiments_generated=0,
            gaps_found=0,
            experiments=[],
            gaps=[],
            coverage_percentage=100.0,
            summary="OK",
        )
        assert report.framework == ComplianceFramework.ISO27001
        assert report.coverage_percentage == 100.0


# ======================================================================
# 13. Framework-specific integration tests
# ======================================================================


class TestFrameworkIntegration:
    """Integration-level tests per framework with realistic component sets."""

    @pytest.fixture()
    def insecure_infra(self):
        """Infrastructure with common compliance gaps."""
        return _graph(
            _comp("db1", "PrimaryDB", ComponentType.DATABASE),
            _comp("ws1", "FrontendWeb", ComponentType.WEB_SERVER),
            _comp("app1", "APIServer", ComponentType.APP_SERVER),
            _comp("cache1", "SessionCache", ComponentType.CACHE),
            _comp("store1", "FileStore", ComponentType.STORAGE),
        )

    def test_soc2_integration(self, insecure_infra):
        gen = ComplianceChaosGenerator(insecure_infra)
        report = gen.generate(ComplianceFramework.SOC2)
        assert report.total_controls == 6
        assert report.chaos_relevant_controls == 6
        assert report.experiments_generated > 0
        assert report.gaps_found > 0
        assert report.coverage_percentage == 100.0

    def test_hipaa_integration(self, insecure_infra):
        gen = ComplianceChaosGenerator(insecure_infra)
        report = gen.generate(ComplianceFramework.HIPAA)
        assert report.total_controls == 5
        assert report.experiments_generated > 0

    def test_pci_dss_integration(self, insecure_infra):
        gen = ComplianceChaosGenerator(insecure_infra)
        report = gen.generate(ComplianceFramework.PCI_DSS)
        assert report.total_controls == 5
        # PCI DSS has NETWORK_SECURITY -> web server should trigger it
        ns_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.NETWORK_SECURITY
        ]
        assert len(ns_exps) >= 1

    def test_iso27001_integration(self, insecure_infra):
        gen = ComplianceChaosGenerator(insecure_infra)
        report = gen.generate(ComplianceFramework.ISO27001)
        assert report.total_controls == 4
        assert report.experiments_generated > 0

    def test_gdpr_integration(self, insecure_infra):
        gen = ComplianceChaosGenerator(insecure_infra)
        report = gen.generate(ComplianceFramework.GDPR)
        assert report.total_controls == 4
        assert report.experiments_generated > 0

    def test_generate_all_integration(self, insecure_infra):
        gen = ComplianceChaosGenerator(insecure_infra)
        reports = gen.generate_all()
        assert len(reports) == 5
        total_experiments = sum(r.experiments_generated for r in reports)
        assert total_experiments > 20  # Should be many experiments across all frameworks


# ======================================================================
# 14. Incident response gap handler returns None
# ======================================================================


class TestIncidentResponseGap:
    """Incident response gap handler should always return None."""

    def test_incident_response_gap_not_generated(self):
        app = _comp("a1", "App")
        gen = ComplianceChaosGenerator(_graph(app))
        report = gen.generate(ComplianceFramework.SOC2)
        ir_gaps = [
            g for g in report.gaps if g.control.category == ControlCategory.INCIDENT_RESPONSE
        ]
        assert len(ir_gaps) == 0


# ======================================================================
# 15. Non-chaos-relevant controls (for coverage of the filter)
# ======================================================================


class TestNonChaosRelevantFilter:
    """Ensure controls with chaos_relevant=False are filtered out of experiments."""

    def test_non_chaos_relevant_control_not_used(self):
        """Manually construct a generator and verify filtering works."""
        # All built-in controls are chaos_relevant=True, so we test
        # coverage of the filter logic via report field consistency
        gen = ComplianceChaosGenerator(_graph(_comp("a1", "App")))
        report = gen.generate(ComplianceFramework.SOC2)
        assert report.chaos_relevant_controls == report.total_controls

    def test_zero_chaos_relevant_gives_100_coverage(self):
        """When relevant==0, coverage should be 100% (vacuously true)."""
        from unittest.mock import patch

        gen = ComplianceChaosGenerator(_graph(_comp("a1", "App")))
        non_relevant = [
            ComplianceControl(
                framework=ComplianceFramework.SOC2,
                category=ControlCategory.DATA_PROTECTION,
                control_id="FAKE",
                description="Not relevant",
                chaos_relevant=False,
            )
        ]
        with patch.object(gen, "_get_controls", return_value=non_relevant):
            report = gen.generate(ComplianceFramework.SOC2)
        assert report.coverage_percentage == 100.0
        assert report.chaos_relevant_controls == 0
        assert report.experiments_generated == 0

    def test_unknown_category_handler_skipped_in_experiments(self):
        """When a control's category has no experiment handler, it is skipped."""
        from unittest.mock import MagicMock

        gen = ComplianceChaosGenerator(_graph(_comp("a1", "App")))
        fake_control = ComplianceControl(
            framework=ComplianceFramework.SOC2,
            category=ControlCategory.DATA_PROTECTION,
            control_id="SKIP",
            description="Skip me",
            chaos_relevant=True,
        )
        # Monkey-patch the category to a value not in the handler map
        fake_control.category = MagicMock()
        result = gen._generate_experiments([fake_control], [_comp("a1", "App")])
        assert result == []

    def test_unknown_category_handler_skipped_in_gaps(self):
        """When a control's category has no gap handler, it is skipped."""
        from unittest.mock import MagicMock

        gen = ComplianceChaosGenerator(_graph(_comp("a1", "App")))
        fake_control = ComplianceControl(
            framework=ComplianceFramework.SOC2,
            category=ControlCategory.DATA_PROTECTION,
            control_id="SKIP",
            description="Skip me",
            chaos_relevant=True,
        )
        fake_control.category = MagicMock()
        result = gen._find_gaps([fake_control], [_comp("a1", "App")])
        assert result == []


# ======================================================================
# 16. DNS, QUEUE, LOAD_BALANCER, EXTERNAL_API, CUSTOM types
# ======================================================================


class TestOtherComponentTypes:
    """Test behavior with non-standard component types."""

    @pytest.mark.parametrize(
        "ctype",
        [
            ComponentType.DNS,
            ComponentType.QUEUE,
            ComponentType.LOAD_BALANCER,
            ComponentType.EXTERNAL_API,
            ComponentType.CUSTOM,
        ],
    )
    def test_non_data_store_no_data_protection_experiment(self, ctype):
        comp = _comp("c1", "Comp", ctype)
        gen = ComplianceChaosGenerator(_graph(comp))
        report = gen.generate(ComplianceFramework.SOC2)
        dp_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.DATA_PROTECTION
        ]
        assert len(dp_exps) == 0

    @pytest.mark.parametrize(
        "ctype",
        [
            ComponentType.DNS,
            ComponentType.QUEUE,
            ComponentType.LOAD_BALANCER,
            ComponentType.EXTERNAL_API,
            ComponentType.CUSTOM,
        ],
    )
    def test_non_data_store_no_backup_experiment(self, ctype):
        comp = _comp("c1", "Comp", ctype)
        gen = ComplianceChaosGenerator(_graph(comp))
        report = gen.generate(ComplianceFramework.SOC2)
        br_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.BACKUP_RECOVERY
        ]
        assert len(br_exps) == 0

    @pytest.mark.parametrize(
        "ctype",
        [
            ComponentType.DATABASE,
            ComponentType.APP_SERVER,
            ComponentType.CACHE,
            ComponentType.QUEUE,
        ],
    )
    def test_non_web_server_no_network_security_experiment(self, ctype):
        comp = _comp("c1", "Comp", ctype)
        gen = ComplianceChaosGenerator(_graph(comp))
        report = gen.generate(ComplianceFramework.PCI_DSS)
        ns_exps = [
            e for e in report.experiments if e.control.category == ControlCategory.NETWORK_SECURITY
        ]
        assert len(ns_exps) == 0
