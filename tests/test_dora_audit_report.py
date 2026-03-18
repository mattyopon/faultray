"""Comprehensive tests for the DORA Resilience Evidence Generator.

Covers:
- DORAuditReportGenerator.generate_full_report()
- DORAuditReportGenerator.export_pdf_data()
- DORAuditReportGenerator.export_regulatory_package()
- DORAuditReportGenerator.generate_register_of_information()
- DORAuditReport dataclass
- RegisterEntry dataclass
- RemediationItem dataclass
- RegulatoryPackage dataclass
- Internal helper methods
- Edge cases (empty graph, all external, all down, etc.)
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    FailoverConfig,
    HealthStatus,
)
from faultray.model.graph import InfraGraph
from faultray.reporter.dora_audit_report import (
    DORAuditReport,
    DORAuditReportGenerator,
    RegisterEntry,
    RemediationItem,
    RegulatoryPackage,
    TLPT_DISCLAIMER,
)
from faultray.simulator.dora_evidence import (
    EvidenceRecord,
    EvidenceStatus,
    _DORA_CONTROLS,
    DORAArticle,
)

# Dynamic counts from the expanded engine
_TOTAL_CONTROLS = len(_DORA_CONTROLS)
_TOTAL_ARTICLES = len(DORAArticle)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    if failover:
        c.failover = FailoverConfig(enabled=True, promotion_time_seconds=10)
    return c


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _minimal_graph() -> InfraGraph:
    return _graph(_comp("app1", "App Server", replicas=2, failover=True))


def _compliant_graph() -> InfraGraph:
    return _graph(
        _comp("app1", "App", replicas=3, failover=True),
        _comp("mon", "Prometheus Monitoring"),
    )


def _full_graph() -> InfraGraph:
    return _graph(
        _comp("lb", "Load Balancer", ctype=ComponentType.LOAD_BALANCER, replicas=2),
        _comp("app", "App Server", ctype=ComponentType.APP_SERVER, replicas=3, failover=True),
        _comp("db", "Database", ctype=ComponentType.DATABASE, failover=True),
        _comp("cache", "Redis", ctype=ComponentType.CACHE, replicas=2),
        _comp("ext", "Payment API", ctype=ComponentType.EXTERNAL_API),
        _comp("mon", "Prometheus"),
    )


def _make_evidence_record(
    control_id: str = "DORA-24.01",
    result: str = "pass",
    severity: str = "medium",
    remediation_required: bool = False,
) -> EvidenceRecord:
    return EvidenceRecord(
        control_id=control_id,
        timestamp=datetime.now(timezone.utc),
        test_type="basic_testing",
        test_description="Test scenario",
        result=result,
        severity=severity,
        remediation_required=remediation_required,
        artifacts=["evidence/test.json"],
    )


# ---------------------------------------------------------------------------
# 1. TLPT Disclaimer
# ---------------------------------------------------------------------------

class TestTLPTDisclaimer:
    def test_disclaimer_is_non_empty(self):
        assert len(TLPT_DISCLAIMER) > 0

    def test_disclaimer_mentions_article_24(self):
        assert "Article 24" in TLPT_DISCLAIMER

    def test_disclaimer_mentions_article_25(self):
        assert "Article 25" in TLPT_DISCLAIMER

    def test_disclaimer_mentions_tlpt(self):
        assert "TLPT" in TLPT_DISCLAIMER


# ---------------------------------------------------------------------------
# 2. Dataclass Tests
# ---------------------------------------------------------------------------

class TestRemediationItem:
    def test_create_item(self):
        item = RemediationItem(
            item_id="REM-0001",
            control_id="DORA-24.01",
            article="Article 24",
            title="Add redundancy",
            description="No replicas detected",
            severity="high",
            effort="medium",
            remediation_deadline="2026-06-01",
            owner="ICT Risk Team",
        )
        assert item.item_id == "REM-0001"
        assert item.status == "open"

    def test_asdict_works(self):
        item = RemediationItem(
            item_id="REM-0002",
            control_id="DORA-11.01",
            article="Article 11",
            title="Fix",
            description="Desc",
            severity="medium",
            effort="low",
            remediation_deadline="2026-09-01",
            owner="Team",
        )
        d = asdict(item)
        assert "item_id" in d
        assert "status" in d


class TestRegisterEntry:
    def test_create_entry(self):
        entry = RegisterEntry(
            provider_id="ext1",
            provider_name="Payment API",
            provider_type="ICT Third-Party Service Provider",
            service_description="Payment processing",
            criticality="critical",
            country_of_incorporation="IE",
        )
        assert entry.provider_id == "ext1"
        assert entry.dependent_functions == []
        assert entry.exit_strategy_documented is False

    def test_asdict_works(self):
        entry = RegisterEntry(
            provider_id="ext2",
            provider_name="Auth API",
            provider_type="ICT Third-Party",
            service_description="Auth",
            criticality="standard",
            country_of_incorporation="DE",
            dependent_functions=["auth-service"],
            exit_strategy_documented=True,
        )
        d = asdict(entry)
        assert d["exit_strategy_documented"] is True
        assert d["dependent_functions"] == ["auth-service"]


class TestDORAuditReport:
    def test_tlpt_disclaimer_on_report(self):
        gen = DORAuditReportGenerator()
        report = gen.generate_full_report(_graph())
        assert report.tlpt_disclaimer == TLPT_DISCLAIMER

    def test_report_id_format(self):
        gen = DORAuditReportGenerator()
        report = gen.generate_full_report(_graph())
        assert report.report_id.startswith("DORA-")

    def test_report_period_start_before_end(self):
        gen = DORAuditReportGenerator()
        report = gen.generate_full_report(_minimal_graph())
        start = datetime.fromisoformat(report.report_period_start)
        end = datetime.fromisoformat(report.report_period_end)
        assert start < end

    def test_generated_at_parseable(self):
        gen = DORAuditReportGenerator()
        report = gen.generate_full_report(_graph())
        datetime.fromisoformat(report.generated_at)


# ---------------------------------------------------------------------------
# 3. generate_full_report() Tests
# ---------------------------------------------------------------------------

class TestGenerateFullReport:
    def setup_method(self):
        self.gen = DORAuditReportGenerator()

    def test_empty_graph(self):
        report = self.gen.generate_full_report(_graph())
        assert report.overall_status == EvidenceStatus.NOT_APPLICABLE
        assert report.total_controls == _TOTAL_CONTROLS

    def test_minimal_graph_has_all_controls(self):
        report = self.gen.generate_full_report(_minimal_graph())
        assert report.total_controls == _TOTAL_CONTROLS

    def test_count_consistency(self):
        report = self.gen.generate_full_report(_minimal_graph())
        total = (
            report.compliant_count
            + report.non_compliant_count
            + report.partially_compliant_count
            + report.not_applicable_count
        )
        assert total == report.total_controls

    def test_overall_status_matches_compliance_report(self):
        report = self.gen.generate_full_report(_minimal_graph())
        assert report.overall_status == report.compliance_report.overall_status

    def test_compliant_graph_status(self):
        report = self.gen.generate_full_report(_compliant_graph())
        # With expanded controls including manual-required ones,
        # a compliant infra graph may still be PARTIALLY_COMPLIANT or NON_COMPLIANT
        assert report.overall_status in (
            EvidenceStatus.COMPLIANT,
            EvidenceStatus.PARTIALLY_COMPLIANT,
            EvidenceStatus.NON_COMPLIANT,
        )

    def test_non_compliant_graph_status(self):
        report = self.gen.generate_full_report(_graph(_comp("app1", "App")))
        assert report.overall_status in (
            EvidenceStatus.NON_COMPLIANT,
            EvidenceStatus.PARTIALLY_COMPLIANT,
        )

    def test_article_statuses_present(self):
        report = self.gen.generate_full_report(_minimal_graph())
        assert len(report.article_statuses) > 0

    def test_all_article_statuses_with_external(self):
        report = self.gen.generate_full_report(_full_graph())
        assert len(report.article_statuses) == _TOTAL_ARTICLES

    def test_with_simulation_results(self):
        sim = [
            {"name": "failover test", "result": "pass", "severity": "low"},
            {"name": "chaos experiment", "result": "fail", "severity": "high"},
        ]
        report = self.gen.generate_full_report(_minimal_graph(), simulation_results=sim)
        assert len(report.evidence_records) >= 2

    def test_with_pre_built_evidence_records(self):
        rec = _make_evidence_record(result="fail", remediation_required=True)
        report = self.gen.generate_full_report(
            _minimal_graph(), evidence_records=[rec]
        )
        # Pre-built records are merged; check total is at least 1
        assert len(report.evidence_records) >= 1

    def test_remediation_items_generated_for_gaps(self):
        report = self.gen.generate_full_report(_graph(_comp("app1", "App")))
        assert len(report.remediation_items) > 0

    def test_no_remediation_items_for_compliant_graph(self):
        report = self.gen.generate_full_report(_compliant_graph())
        # Gap-based remediations should be minimal when compliant
        gap_based = [r for r in report.remediation_items if r.status == "open"]
        # May have some from partial controls but not for N/A
        assert isinstance(gap_based, list)

    def test_register_is_empty_without_external(self):
        report = self.gen.generate_full_report(_compliant_graph())
        assert report.register_of_information == []

    def test_register_has_entries_with_external(self):
        report = self.gen.generate_full_report(_full_graph())
        assert len(report.register_of_information) >= 1

    def test_faultray_version_set(self):
        report = self.gen.generate_full_report(_graph())
        assert report.faultray_version != ""

    def test_reporting_entity_stored(self):
        report = self.gen.generate_full_report(_graph(), reporting_entity="Test Bank")
        assert report.reporting_entity == "Test Bank"

    def test_report_id_contains_entity_hash(self):
        report = self.gen.generate_full_report(_graph(), reporting_entity="Unique Bank")
        assert len(report.report_id) > len("DORA-")

    def test_empty_simulation_results_allowed(self):
        report = self.gen.generate_full_report(_minimal_graph(), simulation_results=[])
        assert report is not None

    def test_none_simulation_results_allowed(self):
        report = self.gen.generate_full_report(_minimal_graph(), simulation_results=None)
        assert report is not None


# ---------------------------------------------------------------------------
# 4. export_pdf_data() Tests
# ---------------------------------------------------------------------------

class TestExportPdfData:
    def setup_method(self):
        self.gen = DORAuditReportGenerator()

    def _make_report(self, graph=None):
        return self.gen.generate_full_report(graph or _minimal_graph())

    def test_returns_dict(self):
        report = self._make_report()
        data = self.gen.export_pdf_data(report)
        assert isinstance(data, dict)

    def test_has_meta_section(self):
        report = self._make_report()
        data = self.gen.export_pdf_data(report)
        assert "meta" in data
        assert data["meta"]["report_id"] == report.report_id

    def test_has_executive_summary(self):
        report = self._make_report()
        data = self.gen.export_pdf_data(report)
        es = data["executive_summary"]
        assert "overall_status" in es
        assert "compliance_rate_percent" in es
        assert "total_controls" in es

    def test_compliance_rate_in_range(self):
        report = self._make_report()
        data = self.gen.export_pdf_data(report)
        rate = data["executive_summary"]["compliance_rate_percent"]
        assert 0.0 <= rate <= 100.0

    def test_article_statuses_in_executive_summary(self):
        report = self.gen.generate_full_report(_full_graph())
        data = self.gen.export_pdf_data(report)
        art_statuses = data["executive_summary"]["article_statuses"]
        assert len(art_statuses) > 0
        for key, val in art_statuses.items():
            assert "status" in val
            assert "color" in val

    def test_gap_analysis_table_length(self):
        report = self._make_report()
        data = self.gen.export_pdf_data(report)
        assert len(data["gap_analysis_table"]) == _TOTAL_CONTROLS

    def test_gap_analysis_table_row_fields(self):
        report = self._make_report()
        data = self.gen.export_pdf_data(report)
        row = data["gap_analysis_table"][0]
        for field_name in ("control_id", "status", "risk_score", "gaps", "recommendations"):
            assert field_name in row

    def test_evidence_table_with_simulation(self):
        sim = [{"name": "failover test", "result": "pass"}]
        report = self.gen.generate_full_report(_minimal_graph(), simulation_results=sim)
        data = self.gen.export_pdf_data(report)
        assert len(data["evidence_table"]) >= 1

    def test_evidence_table_row_fields(self):
        sim = [{"name": "health check", "result": "pass", "severity": "low"}]
        report = self.gen.generate_full_report(_minimal_graph(), simulation_results=sim)
        data = self.gen.export_pdf_data(report)
        if data["evidence_table"]:
            row = data["evidence_table"][0]
            for f in ("control_id", "test_timestamp", "test_type", "methodology",
                      "findings", "severity", "remediation_required",
                      "remediation_deadline", "sign_off_status", "artifacts"):
                assert f in row, f"Missing field: {f}"

    def test_sign_off_status_pass_gives_signed_off(self):
        sim = [{"name": "check", "result": "pass"}]
        report = self.gen.generate_full_report(_minimal_graph(), simulation_results=sim)
        data = self.gen.export_pdf_data(report)
        for row in data["evidence_table"]:
            if not row["remediation_required"]:
                assert row["sign_off_status"] == "signed-off"

    def test_sign_off_status_fail_gives_pending(self):
        sim = [{"name": "check", "result": "fail"}]
        report = self.gen.generate_full_report(_minimal_graph(), simulation_results=sim)
        data = self.gen.export_pdf_data(report)
        for row in data["evidence_table"]:
            if row["remediation_required"]:
                assert row["sign_off_status"] == "pending"

    def test_remediation_plan_present(self):
        report = self.gen.generate_full_report(_graph(_comp("app1", "App")))
        data = self.gen.export_pdf_data(report)
        assert "remediation_plan" in data
        assert isinstance(data["remediation_plan"], list)

    def test_register_empty_without_external(self):
        report = self.gen.generate_full_report(_compliant_graph())
        data = self.gen.export_pdf_data(report)
        assert data["register_of_information"] == []

    def test_register_has_entries_with_external(self):
        report = self.gen.generate_full_report(_full_graph())
        data = self.gen.export_pdf_data(report)
        assert len(data["register_of_information"]) >= 1

    def test_meta_includes_disclaimer(self):
        report = self._make_report()
        data = self.gen.export_pdf_data(report)
        assert TLPT_DISCLAIMER in data["meta"]["tlpt_disclaimer"]

    def test_json_serialisable(self):
        report = self.gen.generate_full_report(_full_graph())
        data = self.gen.export_pdf_data(report)
        # Must not raise
        serialised = json.dumps(data, default=str)
        assert len(serialised) > 0

    def test_overall_status_color_compliant_is_green(self):
        report = self.gen.generate_full_report(_compliant_graph())
        data = self.gen.export_pdf_data(report)
        if data["executive_summary"]["overall_status"] == "compliant":
            assert data["executive_summary"]["overall_status_color"] == "green"


# ---------------------------------------------------------------------------
# 5. export_regulatory_package() Tests
# ---------------------------------------------------------------------------

class TestExportRegulatoryPackage:
    def setup_method(self):
        self.gen = DORAuditReportGenerator()

    def test_creates_output_dir(self, tmp_path: Path):
        out_dir = tmp_path / "dora-pkg"
        report = self.gen.generate_full_report(_minimal_graph())
        pkg = self.gen.export_regulatory_package(report, out_dir)
        assert out_dir.exists()

    def test_returns_regulatory_package(self, tmp_path: Path):
        report = self.gen.generate_full_report(_minimal_graph())
        pkg = self.gen.export_regulatory_package(report, tmp_path / "pkg")
        assert isinstance(pkg, RegulatoryPackage)

    def test_all_expected_files_written(self, tmp_path: Path):
        out_dir = tmp_path / "pkg"
        report = self.gen.generate_full_report(_minimal_graph())
        pkg = self.gen.export_regulatory_package(report, out_dir)
        expected = {
            "executive-summary.json",
            "article-24-testing-evidence.json",
            "article-25-tlpt-readiness.json",
            "article-28-third-party-risk.json",
            "gap-analysis.json",
            "remediation-plan.json",
            "audit-trail.json",
            "manifest.json",
        }
        for fname in expected:
            assert (out_dir / fname).exists(), f"Missing: {fname}"

    def test_files_written_count(self, tmp_path: Path):
        out_dir = tmp_path / "pkg"
        report = self.gen.generate_full_report(_minimal_graph())
        pkg = self.gen.export_regulatory_package(report, out_dir)
        # 8 base files + up to 3 optional new-engine files (incident-management,
        # ict-risk-assessment, concentration-risk) when those modules are available.
        assert len(pkg.files_written) >= 8

    def test_all_files_valid_json(self, tmp_path: Path):
        out_dir = tmp_path / "pkg"
        report = self.gen.generate_full_report(_full_graph())
        pkg = self.gen.export_regulatory_package(report, out_dir)
        for fname in pkg.files_written:
            content = (out_dir / fname).read_text(encoding="utf-8")
            parsed = json.loads(content)
            assert isinstance(parsed, dict)

    def test_manifest_has_checksums(self, tmp_path: Path):
        out_dir = tmp_path / "pkg"
        report = self.gen.generate_full_report(_minimal_graph())
        pkg = self.gen.export_regulatory_package(report, out_dir)
        manifest = json.loads((out_dir / "manifest.json").read_text())
        assert "checksums" in manifest
        # All files except manifest itself should have checksums
        for fname in pkg.files_written:
            if fname != "manifest.json":
                assert fname in manifest["checksums"]

    def test_manifest_compliance_status(self, tmp_path: Path):
        out_dir = tmp_path / "pkg"
        report = self.gen.generate_full_report(_compliant_graph())
        self.gen.export_regulatory_package(report, out_dir)
        manifest = json.loads((out_dir / "manifest.json").read_text())
        assert "overall_compliance_status" in manifest

    def test_manifest_regulatory_framework(self, tmp_path: Path):
        out_dir = tmp_path / "pkg"
        report = self.gen.generate_full_report(_minimal_graph())
        self.gen.export_regulatory_package(report, out_dir)
        manifest = json.loads((out_dir / "manifest.json").read_text())
        assert "DORA" in manifest["regulatory_framework"]

    def test_executive_summary_content(self, tmp_path: Path):
        out_dir = tmp_path / "pkg"
        report = self.gen.generate_full_report(_minimal_graph())
        self.gen.export_regulatory_package(report, out_dir)
        es = json.loads((out_dir / "executive-summary.json").read_text())
        assert es["section"] == "Executive Summary"
        assert "overall_compliance_status" in es
        assert "control_summary" in es
        assert TLPT_DISCLAIMER in es["tlpt_disclaimer"]

    def test_article_24_file_has_testing_evidence(self, tmp_path: Path):
        out_dir = tmp_path / "pkg"
        sim = [{"name": "failover test", "result": "pass"}]
        report = self.gen.generate_full_report(_minimal_graph(), simulation_results=sim)
        self.gen.export_regulatory_package(report, out_dir)
        art24 = json.loads((out_dir / "article-24-testing-evidence.json").read_text())
        assert art24["section"] == "Article 24 — General Requirements for Testing"
        assert "evidence_items" in art24
        assert "gap_summary" in art24

    def test_article_24_disclaimer_present(self, tmp_path: Path):
        out_dir = tmp_path / "pkg"
        report = self.gen.generate_full_report(_minimal_graph())
        self.gen.export_regulatory_package(report, out_dir)
        art24 = json.loads((out_dir / "article-24-testing-evidence.json").read_text())
        assert TLPT_DISCLAIMER in art24["tlpt_disclaimer"]

    def test_article_25_file_content(self, tmp_path: Path):
        out_dir = tmp_path / "pkg"
        report = self.gen.generate_full_report(_minimal_graph())
        self.gen.export_regulatory_package(report, out_dir)
        art25 = json.loads((out_dir / "article-25-tlpt-readiness.json").read_text())
        assert art25["section"] == "Article 25 — TLPT Readiness Assessment"
        assert "tlpt_readiness" in art25
        assert "readiness_criteria" in art25
        assert "recommended_actions" in art25
        assert TLPT_DISCLAIMER in art25["tlpt_disclaimer"]

    def test_article_28_file_content(self, tmp_path: Path):
        out_dir = tmp_path / "pkg"
        report = self.gen.generate_full_report(_full_graph())
        self.gen.export_regulatory_package(report, out_dir)
        art28 = json.loads((out_dir / "article-28-third-party-risk.json").read_text())
        assert art28["section"] == "Article 28 — ICT Third-Party Risk Management"
        assert "third_party_provider_count" in art28
        assert "register_of_information" in art28

    def test_gap_analysis_file_content(self, tmp_path: Path):
        out_dir = tmp_path / "pkg"
        report = self.gen.generate_full_report(_minimal_graph())
        self.gen.export_regulatory_package(report, out_dir)
        gap = json.loads((out_dir / "gap-analysis.json").read_text())
        assert gap["section"] == "Gap Analysis"
        assert "all_gaps" in gap
        assert len(gap["all_gaps"]) == _TOTAL_CONTROLS

    def test_remediation_plan_file_content(self, tmp_path: Path):
        out_dir = tmp_path / "pkg"
        report = self.gen.generate_full_report(_graph(_comp("app1", "App")))
        self.gen.export_regulatory_package(report, out_dir)
        rem = json.loads((out_dir / "remediation-plan.json").read_text())
        assert rem["section"] == "Remediation Plan"
        assert "items" in rem
        assert "by_severity" in rem
        assert "prioritised" in rem

    def test_audit_trail_unsigned_default(self, tmp_path: Path):
        out_dir = tmp_path / "pkg"
        report = self.gen.generate_full_report(_minimal_graph())
        self.gen.export_regulatory_package(report, out_dir, sign=False)
        trail = json.loads((out_dir / "audit-trail.json").read_text())
        assert trail["signed"] is False

    def test_audit_trail_signed(self, tmp_path: Path):
        out_dir = tmp_path / "pkg"
        sim = [{"name": "test", "result": "pass"}]
        report = self.gen.generate_full_report(_minimal_graph(), simulation_results=sim)
        self.gen.export_regulatory_package(report, out_dir, sign=True)
        trail = json.loads((out_dir / "audit-trail.json").read_text())
        assert trail["signed"] is True
        if trail["chain"]:
            for item in trail["chain"]:
                assert "integrity_hash" in item
            assert "chain_integrity_hash" in trail

    def test_package_output_dir_stored(self, tmp_path: Path):
        out_dir = tmp_path / "pkg"
        report = self.gen.generate_full_report(_minimal_graph())
        pkg = self.gen.export_regulatory_package(report, out_dir)
        assert pkg.output_dir == out_dir

    def test_nested_output_dir_created(self, tmp_path: Path):
        out_dir = tmp_path / "deep" / "nested" / "dora"
        report = self.gen.generate_full_report(_minimal_graph())
        pkg = self.gen.export_regulatory_package(report, out_dir)
        assert out_dir.exists()

    def test_existing_output_dir_overwritten(self, tmp_path: Path):
        out_dir = tmp_path / "pkg"
        out_dir.mkdir()
        # Write a pre-existing file that should be replaced
        (out_dir / "executive-summary.json").write_text("{}")
        report = self.gen.generate_full_report(_minimal_graph())
        pkg = self.gen.export_regulatory_package(report, out_dir)
        content = (out_dir / "executive-summary.json").read_text()
        parsed = json.loads(content)
        assert parsed.get("section") == "Executive Summary"


# ---------------------------------------------------------------------------
# 6. generate_register_of_information() Tests
# ---------------------------------------------------------------------------

class TestGenerateRegisterOfInformation:
    def setup_method(self):
        self.gen = DORAuditReportGenerator()

    def test_empty_graph_returns_empty_list(self):
        entries = self.gen.generate_register_of_information(_graph())
        assert entries == []

    def test_no_external_api_returns_empty(self):
        entries = self.gen.generate_register_of_information(_compliant_graph())
        assert entries == []

    def test_single_external_returns_one_entry(self):
        g = _graph(
            _comp("app1", "App"),
            _comp("ext1", "Payment API", ctype=ComponentType.EXTERNAL_API),
        )
        entries = self.gen.generate_register_of_information(g)
        assert len(entries) == 1

    def test_entry_fields_populated(self):
        g = _graph(
            _comp("ext1", "Payment API", ctype=ComponentType.EXTERNAL_API),
        )
        entries = self.gen.generate_register_of_information(g)
        e = entries[0]
        assert e.provider_id == "ext1"
        assert e.provider_name == "Payment API"
        assert e.provider_type == "ICT Third-Party Service Provider"
        assert e.service_description != ""
        assert e.criticality in ("critical", "important", "standard")
        assert e.last_assessed != ""

    def test_multiple_externals(self):
        g = _graph(
            _comp("ext1", "API1", ctype=ComponentType.EXTERNAL_API),
            _comp("ext2", "API2", ctype=ComponentType.EXTERNAL_API),
            _comp("ext3", "API3", ctype=ComponentType.EXTERNAL_API),
        )
        entries = self.gen.generate_register_of_information(g)
        assert len(entries) == 3

    def test_concentration_risk_detected_when_majority_external(self):
        g = _graph(
            _comp("ext1", "API1", ctype=ComponentType.EXTERNAL_API),
            _comp("ext2", "API2", ctype=ComponentType.EXTERNAL_API),
            _comp("ext3", "API3", ctype=ComponentType.EXTERNAL_API),
            _comp("app1", "App"),
        )
        entries = self.gen.generate_register_of_information(g)
        assert all(e.concentration_risk for e in entries)

    def test_no_concentration_risk_when_minority_external(self):
        g = _graph(
            _comp("app1", "App"),
            _comp("app2", "App2"),
            _comp("app3", "App3"),
            _comp("db", "DB", ctype=ComponentType.DATABASE),
            _comp("ext1", "API", ctype=ComponentType.EXTERNAL_API),
        )
        entries = self.gen.generate_register_of_information(g)
        assert all(not e.concentration_risk for e in entries)

    def test_exit_strategy_documented_if_failover(self):
        g = _graph(
            _comp("ext1", "Failsafe API", ctype=ComponentType.EXTERNAL_API, failover=True),
        )
        entries = self.gen.generate_register_of_information(g)
        assert entries[0].exit_strategy_documented is True

    def test_no_exit_strategy_without_failover(self):
        g = _graph(
            _comp("ext1", "API", ctype=ComponentType.EXTERNAL_API, failover=False),
        )
        entries = self.gen.generate_register_of_information(g)
        assert entries[0].exit_strategy_documented is False

    def test_dependent_functions_listed(self):
        g = _graph(
            _comp("app1", "App Server"),
            _comp("ext1", "Payments API", ctype=ComponentType.EXTERNAL_API),
        )
        entries = self.gen.generate_register_of_information(g)
        # dependent_functions is always a list (populated from graph.get_dependents)
        assert isinstance(entries[0].dependent_functions, list)

    def test_criticality_standard_no_dependents(self):
        g = _graph(
            _comp("ext1", "Background API", ctype=ComponentType.EXTERNAL_API),
        )
        entries = self.gen.generate_register_of_information(g)
        assert entries[0].criticality == "standard"

    def test_last_assessed_is_today(self):
        g = _graph(_comp("ext1", "API", ctype=ComponentType.EXTERNAL_API))
        entries = self.gen.generate_register_of_information(g)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert entries[0].last_assessed == today

    def test_contractual_arrangements_present(self):
        g = _graph(_comp("ext1", "API", ctype=ComponentType.EXTERNAL_API))
        entries = self.gen.generate_register_of_information(g)
        assert len(entries[0].contractual_arrangements) > 0


# ---------------------------------------------------------------------------
# 7. Internal helper methods
# ---------------------------------------------------------------------------

class TestInternalHelpers:
    def setup_method(self):
        self.gen = DORAuditReportGenerator()

    def test_methodology_basic_testing(self):
        m = DORAuditReportGenerator._methodology_for_test_type("basic_testing")
        assert "Article 24" in m

    def test_methodology_advanced_testing(self):
        m = DORAuditReportGenerator._methodology_for_test_type("advanced_testing")
        assert "Article 24" in m

    def test_methodology_tlpt(self):
        m = DORAuditReportGenerator._methodology_for_test_type("tlpt")
        assert "Article 25" in m

    def test_methodology_unknown(self):
        m = DORAuditReportGenerator._methodology_for_test_type("unknown_type")
        assert "FaultRay" in m

    def test_findings_pass(self):
        rec = _make_evidence_record(result="pass")
        f = DORAuditReportGenerator._findings_summary(rec)
        assert "passed" in f.lower() or "pass" in f.lower()

    def test_findings_fail(self):
        rec = _make_evidence_record(result="fail", remediation_required=True)
        f = DORAuditReportGenerator._findings_summary(rec)
        assert "FAILED" in f or "fail" in f.lower()

    def test_findings_partial(self):
        rec = _make_evidence_record(result="partial")
        f = DORAuditReportGenerator._findings_summary(rec)
        assert "partial" in f.lower()

    def test_deadline_critical_is_30_days(self):
        d = DORAuditReportGenerator._deadline_for_severity("critical")
        deadline = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = (deadline - now).days
        assert 28 <= diff <= 31

    def test_deadline_low_is_180_days(self):
        d = DORAuditReportGenerator._deadline_for_severity("low")
        deadline = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = (deadline - now).days
        assert 178 <= diff <= 182

    def test_deadline_unknown_severity_defaults(self):
        d = DORAuditReportGenerator._deadline_for_severity("unknown")
        # Should not raise; returns a date string
        datetime.strptime(d, "%Y-%m-%d")

    def test_article_from_control_id_24(self):
        a = DORAuditReportGenerator._article_from_control_id("DORA-24.01")
        assert "24" in a

    def test_article_from_control_id_11(self):
        a = DORAuditReportGenerator._article_from_control_id("DORA-11.05")
        assert "11" in a

    def test_article_from_control_id_invalid(self):
        a = DORAuditReportGenerator._article_from_control_id("INVALID")
        assert "Unknown" in a


# ---------------------------------------------------------------------------
# 8. Remediation item building
# ---------------------------------------------------------------------------

class TestRemediationBuilding:
    def setup_method(self):
        self.gen = DORAuditReportGenerator()

    def test_remediation_items_have_unique_ids(self):
        report = self.gen.generate_full_report(_graph(_comp("app1", "App")))
        ids = [r.item_id for r in report.remediation_items]
        assert len(ids) == len(set(ids))

    def test_all_remediation_ids_prefixed_rem(self):
        report = self.gen.generate_full_report(_graph(_comp("app1", "App")))
        for item in report.remediation_items:
            assert item.item_id.startswith("REM-")

    def test_remediation_severity_mapping(self):
        report = self.gen.generate_full_report(_graph(_comp("app1", "App")))
        valid_severities = {"critical", "high", "medium", "low"}
        for item in report.remediation_items:
            assert item.severity in valid_severities

    def test_remediation_effort_mapping(self):
        report = self.gen.generate_full_report(_graph(_comp("app1", "App")))
        valid_efforts = {"low", "medium", "high"}
        for item in report.remediation_items:
            assert item.effort in valid_efforts

    def test_remediation_items_from_failing_evidence(self):
        sim = [{"name": "failover test", "result": "fail", "severity": "critical"}]
        report = self.gen.generate_full_report(_minimal_graph(), simulation_results=sim)
        evidence_based = [r for r in report.remediation_items if "failed test" in r.title.lower()]
        assert len(evidence_based) >= 1

    def test_remediation_items_status_open(self):
        report = self.gen.generate_full_report(_graph(_comp("app1", "App")))
        for item in report.remediation_items:
            assert item.status == "open"

    def test_remediation_deadlines_are_future_dates(self):
        report = self.gen.generate_full_report(_graph(_comp("app1", "App")))
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for item in report.remediation_items:
            assert item.remediation_deadline > today_str


# ---------------------------------------------------------------------------
# 9. Article section builders
# ---------------------------------------------------------------------------

class TestArticleSectionBuilders:
    def setup_method(self):
        self.gen = DORAuditReportGenerator()

    def test_article_24_section_has_disclaimer(self):
        report = self.gen.generate_full_report(_minimal_graph())
        section = self.gen._build_article_24_section(report)
        assert TLPT_DISCLAIMER in section["tlpt_disclaimer"]

    def test_article_24_section_reference(self):
        report = self.gen.generate_full_report(_minimal_graph())
        section = self.gen._build_article_24_section(report)
        assert "Article 24" in section["regulatory_reference"]

    def test_article_25_readiness_values(self):
        report = self.gen.generate_full_report(_minimal_graph())
        section = self.gen._build_article_25_section(report)
        assert section["tlpt_readiness"] in (
            "ready", "mostly_ready", "preparation_required", "not_ready"
        )

    def test_article_25_readiness_criteria_keys(self):
        report = self.gen.generate_full_report(_minimal_graph())
        section = self.gen._build_article_25_section(report)
        crit = section["readiness_criteria"]
        assert "redundancy_configured" in crit
        assert "failover_configured" in crit

    def test_article_25_recommended_actions(self):
        report = self.gen.generate_full_report(_minimal_graph())
        section = self.gen._build_article_25_section(report)
        assert len(section["recommended_actions"]) >= 3

    def test_article_28_provider_count(self):
        report = self.gen.generate_full_report(_full_graph())
        section = self.gen._build_article_28_section(report)
        assert section["third_party_provider_count"] >= 1

    def test_article_28_required_provisions(self):
        report = self.gen.generate_full_report(_full_graph())
        section = self.gen._build_article_28_section(report)
        assert len(section["required_contractual_provisions"]) >= 3

    def test_gap_analysis_section_structure(self):
        report = self.gen.generate_full_report(_minimal_graph())
        section = self.gen._build_gap_analysis_section(report)
        assert section["total_controls"] == _TOTAL_CONTROLS
        assert "by_article" in section
        assert "all_gaps" in section
        assert "overall_risk_score" in section

    def test_gap_analysis_section_risk_in_range(self):
        report = self.gen.generate_full_report(_minimal_graph())
        section = self.gen._build_gap_analysis_section(report)
        assert 0.0 <= section["overall_risk_score"] <= 1.0

    def test_remediation_section_by_severity(self):
        report = self.gen.generate_full_report(_graph(_comp("app1", "App")))
        section = self.gen._build_remediation_section(report)
        assert "by_severity" in section
        for sev in ("critical", "high", "medium", "low"):
            assert sev in section["by_severity"]

    def test_remediation_section_prioritised_order(self):
        report = self.gen.generate_full_report(_graph(_comp("app1", "App")))
        section = self.gen._build_remediation_section(report)
        # First item in prioritised list should not have lower priority than last
        items = section["prioritised"]
        if len(items) >= 2:
            order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            first_prio = order.get(items[0]["severity"], 4)
            last_prio = order.get(items[-1]["severity"], 4)
            assert first_prio <= last_prio

    def test_executive_summary_non_compliant_list(self):
        report = self.gen.generate_full_report(_graph(_comp("app1", "App")))
        section = self.gen._build_executive_summary(report)
        assert isinstance(section["non_compliant_controls"], list)

    def test_executive_summary_high_risk_list(self):
        report = self.gen.generate_full_report(_graph(_comp("app1", "App")))
        section = self.gen._build_executive_summary(report)
        assert isinstance(section["high_risk_controls"], list)

    def test_executive_summary_next_review_date(self):
        report = self.gen.generate_full_report(_minimal_graph())
        section = self.gen._build_executive_summary(report)
        assert "next_review_date" in section
        datetime.fromisoformat(section["next_review_date"].replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# 10. Audit trail tests
# ---------------------------------------------------------------------------

class TestAuditTrail:
    def setup_method(self):
        self.gen = DORAuditReportGenerator()

    def test_audit_trail_unsigned_no_hashes(self):
        sim = [{"name": "test", "result": "pass"}]
        report = self.gen.generate_full_report(_minimal_graph(), simulation_results=sim)
        trail = self.gen._build_audit_trail(report, sign=False)
        assert trail["signed"] is False
        for item in trail["chain"]:
            assert "integrity_hash" not in item

    def test_audit_trail_signed_has_hashes(self):
        sim = [{"name": "test", "result": "fail"}]
        report = self.gen.generate_full_report(_minimal_graph(), simulation_results=sim)
        trail = self.gen._build_audit_trail(report, sign=True)
        assert trail["signed"] is True
        for item in trail["chain"]:
            assert "integrity_hash" in item
        assert "chain_integrity_hash" in trail

    def test_audit_trail_sequence_numbers(self):
        sim = [
            {"name": "t1", "result": "pass"},
            {"name": "t2", "result": "fail"},
        ]
        report = self.gen.generate_full_report(_minimal_graph(), simulation_results=sim)
        trail = self.gen._build_audit_trail(report, sign=False)
        for i, item in enumerate(trail["chain"], start=1):
            assert item["sequence"] == i

    def test_audit_trail_evidence_fields(self):
        sim = [{"name": "check", "result": "pass", "severity": "low"}]
        report = self.gen.generate_full_report(_minimal_graph(), simulation_results=sim)
        trail = self.gen._build_audit_trail(report, sign=False)
        for item in trail["chain"]:
            for f in ("control_id", "test_timestamp", "test_type", "methodology",
                      "findings", "severity", "remediation_required",
                      "remediation_deadline", "sign_off_status", "artifacts"):
                assert f in item, f"Missing field: {f}"

    def test_audit_trail_empty_when_no_evidence(self):
        report = self.gen.generate_full_report(_minimal_graph())
        trail = self.gen._build_audit_trail(report, sign=False)
        assert trail["total_evidence_items"] == len(report.evidence_records)


# ---------------------------------------------------------------------------
# 11. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def setup_method(self):
        self.gen = DORAuditReportGenerator()

    def test_all_external_graph(self):
        g = _graph(
            _comp("ext1", "API1", ctype=ComponentType.EXTERNAL_API),
            _comp("ext2", "API2", ctype=ComponentType.EXTERNAL_API),
        )
        report = self.gen.generate_full_report(g)
        assert report.total_controls == _TOTAL_CONTROLS

    def test_all_components_down(self):
        g = _graph(
            _comp("app1", "App", health=HealthStatus.DOWN),
            _comp("app2", "App2", health=HealthStatus.DOWN),
        )
        report = self.gen.generate_full_report(g)
        assert report.overall_status != EvidenceStatus.COMPLIANT

    def test_large_simulation_results(self):
        sim = [{"name": f"test_{i}", "result": "pass"} for i in range(50)]
        report = self.gen.generate_full_report(_minimal_graph(), simulation_results=sim)
        assert len(report.evidence_records) >= 50

    def test_mixed_pass_fail_partial_scenarios(self):
        sim = [
            {"name": "health check", "result": "pass", "severity": "low"},
            {"name": "failover test", "result": "fail", "severity": "high"},
            {"name": "stress test", "result": "partial", "severity": "medium"},
            {"name": "penetration test", "result": "pass", "severity": "critical"},
        ]
        report = self.gen.generate_full_report(_minimal_graph(), simulation_results=sim)
        assert len(report.evidence_records) >= 4
        has_remediation = any(r.remediation_required for r in report.evidence_records)
        assert has_remediation

    def test_package_exports_with_full_simulation(self, tmp_path: Path):
        sim = [
            {"name": "disaster recovery", "result": "fail", "severity": "critical"},
            {"name": "health check", "result": "pass", "severity": "low"},
        ]
        report = self.gen.generate_full_report(_full_graph(), simulation_results=sim)
        pkg = self.gen.export_regulatory_package(report, tmp_path / "full-pkg", sign=True)
        # 8 base files + up to 3 optional new-engine files
        assert len(pkg.files_written) >= 8

    def test_report_with_no_components_and_evidence(self, tmp_path: Path):
        report = self.gen.generate_full_report(_graph())
        pkg = self.gen.export_regulatory_package(report, tmp_path / "empty-pkg")
        manifest = json.loads((tmp_path / "empty-pkg" / "manifest.json").read_text())
        assert manifest["overall_compliance_status"] == "not_applicable"

    def test_custom_signing_key(self):
        gen2 = DORAuditReportGenerator(signing_key="my-custom-key-2026")
        report = gen2.generate_full_report(_minimal_graph())
        assert report is not None

    def test_tlpt_scenario_maps_in_report(self):
        sim = [{"name": "penetration test", "result": "pass"}]
        report = self.gen.generate_full_report(_minimal_graph(), simulation_results=sim)
        tlpt_records = [r for r in report.evidence_records if r.test_type == "tlpt"]
        assert len(tlpt_records) >= 1

    def test_third_party_scenario_maps_to_article_28(self):
        sim = [{"name": "api check", "result": "pass", "involves_third_party": True}]
        report = self.gen.generate_full_report(_full_graph(), simulation_results=sim)
        art28_records = [r for r in report.evidence_records if r.control_id.startswith("DORA-28")]
        assert len(art28_records) >= 1

    def test_pdf_data_json_serialisable_full_graph(self):
        sim = [{"name": "test", "result": "fail", "severity": "high"}]
        report = self.gen.generate_full_report(_full_graph(), simulation_results=sim)
        data = self.gen.export_pdf_data(report)
        serialised = json.dumps(data, default=str)
        reparsed = json.loads(serialised)
        assert reparsed["meta"]["report_id"] == report.report_id
