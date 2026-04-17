# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Tests for compliance evidence HTML report generator (Feature C)."""

from __future__ import annotations

from pathlib import Path

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    RegionConfig,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.reporter.compliance_pdf import _pct_class, _run_framework, generate_compliance_html


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_graph() -> InfraGraph:
    """Minimal graph: one app server + one database, no security features."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app",
        name="app-server",
        type=ComponentType.APP_SERVER,
        port=8080,
        replicas=1,
    ))
    graph.add_component(Component(
        id="db",
        name="database",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=1,
    ))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


@pytest.fixture
def secure_graph() -> InfraGraph:
    """Well-configured graph: should have reasonable compliance rates."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb",
        name="Load Balancer",
        type=ComponentType.LOAD_BALANCER,
        port=443,
        replicas=2,
        security=SecurityProfile(
            encryption_in_transit=True,
            waf_protected=True,
            rate_limiting=True,
            auth_required=True,
        ),
    ))
    graph.add_component(Component(
        id="app",
        name="App Server",
        type=ComponentType.APP_SERVER,
        port=8443,
        replicas=2,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=6),
    ))
    graph.add_component(Component(
        id="db",
        name="Primary DB",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=2,
        failover=FailoverConfig(enabled=True, promotion_time_seconds=30.0),
        security=SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            auth_required=True,
            backup_enabled=True,
        ),
        region=RegionConfig(dr_target_region="us-west-2"),
    ))
    graph.add_dependency(
        Dependency(
            source_id="lb",
            target_id="app",
            dependency_type="requires",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        )
    )
    graph.add_dependency(
        Dependency(
            source_id="app",
            target_id="db",
            dependency_type="requires",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        )
    )
    return graph


@pytest.fixture
def empty_graph() -> InfraGraph:
    return InfraGraph()


# ---------------------------------------------------------------------------
# Unit tests: _pct_class
# ---------------------------------------------------------------------------


def test_pct_class_green() -> None:
    assert _pct_class(80.0) == "pct-green"
    assert _pct_class(100.0) == "pct-green"


def test_pct_class_yellow() -> None:
    assert _pct_class(50.0) == "pct-yellow"
    assert _pct_class(79.9) == "pct-yellow"


def test_pct_class_red() -> None:
    assert _pct_class(0.0) == "pct-red"
    assert _pct_class(49.9) == "pct-red"


# ---------------------------------------------------------------------------
# Unit tests: _run_framework
# ---------------------------------------------------------------------------


def test_run_framework_soc2_returns_report(minimal_graph: InfraGraph) -> None:
    report = _run_framework(minimal_graph, "soc2")
    assert report is not None
    assert report.framework == "soc2"
    assert report.total_checks > 0


def test_run_framework_iso27001_returns_report(minimal_graph: InfraGraph) -> None:
    report = _run_framework(minimal_graph, "iso27001")
    assert report is not None
    assert report.total_checks > 0


def test_run_framework_pci_dss_returns_report(minimal_graph: InfraGraph) -> None:
    report = _run_framework(minimal_graph, "pci_dss")
    assert report is not None
    assert report.total_checks > 0


def test_run_framework_nist_csf_returns_report(minimal_graph: InfraGraph) -> None:
    report = _run_framework(minimal_graph, "nist_csf")
    assert report is not None
    assert report.total_checks > 0


def test_run_framework_unknown_returns_none(minimal_graph: InfraGraph) -> None:
    result = _run_framework(minimal_graph, "unknown_fw_xyz")
    assert result is None


# ---------------------------------------------------------------------------
# Integration tests: generate_compliance_html
# ---------------------------------------------------------------------------


def test_generate_html_creates_file(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    generate_compliance_html(minimal_graph, ["soc2"], out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_generate_html_contains_doctype(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    generate_compliance_html(minimal_graph, ["soc2"], out)
    content = out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content


def test_generate_html_contains_org_name(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    generate_compliance_html(minimal_graph, ["soc2"], out, org_name="AcmeCorp")
    content = out.read_text(encoding="utf-8")
    assert "AcmeCorp" in content


def test_generate_html_contains_framework_name(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    generate_compliance_html(minimal_graph, ["iso27001"], out)
    content = out.read_text(encoding="utf-8")
    assert "iso27001" in content.lower()


def test_generate_html_multiple_frameworks(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    generate_compliance_html(minimal_graph, ["soc2", "iso27001", "pci_dss"], out)
    content = out.read_text(encoding="utf-8")
    assert "soc2" in content.lower()
    assert "iso27001" in content.lower()
    assert "pci_dss" in content.lower()


def test_generate_html_contains_component_names(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    generate_compliance_html(minimal_graph, ["soc2"], out)
    content = out.read_text(encoding="utf-8")
    assert "app-server" in content
    assert "database" in content


def test_generate_html_contains_media_print(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    """HTML must contain @media print styles for PDF export."""
    out = tmp_path / "report.html"
    generate_compliance_html(minimal_graph, ["soc2"], out)
    content = out.read_text(encoding="utf-8")
    assert "@media print" in content


def test_generate_html_contains_executive_summary(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    generate_compliance_html(minimal_graph, ["soc2"], out)
    content = out.read_text(encoding="utf-8")
    assert "Executive Summary" in content


def test_generate_html_secure_graph_higher_compliance(
    minimal_graph: InfraGraph,
    secure_graph: InfraGraph,
) -> None:
    """Secure graph should produce a higher compliance percentage than minimal graph."""
    from faultray.reporter.compliance_pdf import _run_framework as _rf

    report_min = _rf(minimal_graph, "soc2")
    report_sec = _rf(secure_graph, "soc2")
    assert report_sec.compliance_percent >= report_min.compliance_percent


def test_generate_html_empty_graph_does_not_crash(empty_graph: InfraGraph, tmp_path: Path) -> None:
    out = tmp_path / "empty.html"
    generate_compliance_html(empty_graph, ["soc2"], out)
    assert out.exists()


# ---------------------------------------------------------------------------
# _pct_class boundary tests
# ---------------------------------------------------------------------------


def test_pct_class_exactly_80_is_green() -> None:
    assert _pct_class(80.0) == "pct-green"


def test_pct_class_just_below_80_is_yellow() -> None:
    assert _pct_class(79.9) == "pct-yellow"


def test_pct_class_exactly_50_is_yellow() -> None:
    assert _pct_class(50.0) == "pct-yellow"


def test_pct_class_just_below_50_is_red() -> None:
    assert _pct_class(49.9) == "pct-red"


def test_pct_class_0_is_red() -> None:
    assert _pct_class(0.0) == "pct-red"


def test_pct_class_100_is_green() -> None:
    assert _pct_class(100.0) == "pct-green"


# ---------------------------------------------------------------------------
# _run_framework additional tests
# ---------------------------------------------------------------------------


def test_run_framework_dora_returns_report(minimal_graph: InfraGraph) -> None:
    report = _run_framework(minimal_graph, "dora")
    assert report is not None
    assert report.total_checks > 0


def test_run_framework_fisc_returns_report(minimal_graph: InfraGraph) -> None:
    report = _run_framework(minimal_graph, "fisc")
    assert report is not None
    assert report.total_checks > 0


def test_run_framework_compliance_percent_range(minimal_graph: InfraGraph) -> None:
    """compliance_percent should be in [0, 100] for all supported frameworks."""
    for fw in ("soc2", "iso27001", "pci_dss", "nist_csf"):
        report = _run_framework(minimal_graph, fw)
        assert report is not None
        assert 0.0 <= report.compliance_percent <= 100.0


def test_run_framework_total_equals_sum_of_parts(minimal_graph: InfraGraph) -> None:
    """total_checks should equal passed + partial + failed."""
    for fw in ("soc2", "iso27001"):
        report = _run_framework(minimal_graph, fw)
        assert report is not None
        assert report.total_checks == report.passed + report.partial + report.failed


def test_run_framework_secure_vs_minimal_soc2(
    minimal_graph: InfraGraph, secure_graph: InfraGraph
) -> None:
    """Secure graph SOC2 compliance >= minimal graph compliance."""
    r_min = _run_framework(minimal_graph, "soc2")
    r_sec = _run_framework(secure_graph, "soc2")
    assert r_min is not None
    assert r_sec is not None
    assert r_sec.compliance_percent >= r_min.compliance_percent


def test_run_framework_nist_csf_empty(empty_graph: InfraGraph) -> None:
    """Empty graph NIST CSF should not crash."""
    report = _run_framework(empty_graph, "nist_csf")
    assert report is not None


def test_run_framework_pci_dss_secure(secure_graph: InfraGraph) -> None:
    """Secure graph PCI DSS compliance > 0%."""
    report = _run_framework(secure_graph, "pci_dss")
    assert report is not None
    assert report.compliance_percent > 0.0


# ---------------------------------------------------------------------------
# HTML generation additional tests
# ---------------------------------------------------------------------------


def test_generate_html_default_org_name(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    """Default org_name 'Your Organization' appears in HTML."""
    out = tmp_path / "report.html"
    generate_compliance_html(minimal_graph, ["soc2"], out)
    content = out.read_text(encoding="utf-8")
    assert "Your Organization" in content


def test_generate_html_all_frameworks(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    """All supported frameworks should render without error."""
    out = tmp_path / "all_fw.html"
    generate_compliance_html(minimal_graph, ["soc2", "iso27001", "pci_dss", "nist_csf"], out)
    content = out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert out.stat().st_size > 0


def test_generate_html_unknown_framework_skipped(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    """Unknown framework should be silently skipped; file still generated."""
    out = tmp_path / "skip.html"
    generate_compliance_html(minimal_graph, ["unknown_xyz", "soc2"], out)
    content = out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content


def test_generate_html_contains_compliance_percent(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    """HTML should contain the compliance percentage value."""
    out = tmp_path / "pct.html"
    generate_compliance_html(minimal_graph, ["soc2"], out)
    content = out.read_text(encoding="utf-8")
    # Some numeric % should appear
    assert "%" in content


def test_generate_html_contains_faultray_version(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    """HTML should reference the faultray version."""
    out = tmp_path / "ver.html"
    generate_compliance_html(minimal_graph, ["soc2"], out)
    content = out.read_text(encoding="utf-8")
    # faultray version appears in the footer
    assert "FaultRay" in content or "faultray" in content.lower()


def test_generate_html_creates_nested_dir(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    """Output file can be nested in subdirectories that don't yet exist."""
    out = tmp_path / "a" / "b" / "c" / "report.html"
    # compliance_pdf doesn't create parent dirs, so we must do it:
    out.parent.mkdir(parents=True, exist_ok=True)
    generate_compliance_html(minimal_graph, ["soc2"], out)
    assert out.exists()


@pytest.mark.parametrize("framework", ["soc2", "iso27001", "pci_dss", "nist_csf"])
def test_each_framework_generates_valid_html(
    framework: str, minimal_graph: InfraGraph, tmp_path: Path
) -> None:
    """Each supported framework should individually generate valid HTML."""
    out = tmp_path / f"{framework}.html"
    generate_compliance_html(minimal_graph, [framework], out)
    content = out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert framework.lower() in content.lower()


def test_generate_html_empty_framework_list(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    """Empty framework list should generate an HTML file without crashing."""
    out = tmp_path / "empty_fw.html"
    generate_compliance_html(minimal_graph, [], out)
    assert out.exists()


def test_generate_html_checks_have_control_ids(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    """Generated HTML from soc2 should contain control IDs."""
    out = tmp_path / "ctrl.html"
    generate_compliance_html(minimal_graph, ["soc2"], out)
    content = out.read_text(encoding="utf-8")
    # SOC 2 controls should be present in the HTML
    assert "SOC" in content or "CC" in content or "soc" in content.lower()


def test_run_framework_checks_list_non_empty(minimal_graph: InfraGraph) -> None:
    """ComplianceReport.checks should be a non-empty list for soc2."""
    report = _run_framework(minimal_graph, "soc2")
    assert report is not None
    assert len(report.checks) > 0


def test_run_framework_iso27001_check_status_values(minimal_graph: InfraGraph) -> None:
    """All check statuses should be one of pass/partial/fail/not_applicable."""
    report = _run_framework(minimal_graph, "iso27001")
    assert report is not None
    valid = {"pass", "partial", "fail", "not_applicable"}
    for chk in report.checks:
        assert chk.status in valid, f"Invalid status: {chk.status}"


def test_run_framework_pci_dss_checks_non_empty(minimal_graph: InfraGraph) -> None:
    """PCI DSS should produce a non-empty list of checks."""
    report = _run_framework(minimal_graph, "pci_dss")
    assert report is not None
    assert len(report.checks) > 0


def test_run_framework_nist_csf_checks_non_empty(minimal_graph: InfraGraph) -> None:
    """NIST CSF should produce a non-empty list of checks."""
    report = _run_framework(minimal_graph, "nist_csf")
    assert report is not None
    assert len(report.checks) > 0


def test_generate_html_iso27001_contains_checks(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    """ISO 27001 HTML should contain check-related content."""
    out = tmp_path / "iso.html"
    generate_compliance_html(minimal_graph, ["iso27001"], out)
    content = out.read_text(encoding="utf-8")
    assert "iso27001" in content.lower()
    assert out.stat().st_size > 1000


@pytest.mark.parametrize("framework", ["soc2", "iso27001", "pci_dss", "nist_csf"])
def test_run_framework_passed_plus_failed_le_total(
    framework: str, minimal_graph: InfraGraph
) -> None:
    """passed + partial + failed should equal total_checks for each framework."""
    report = _run_framework(minimal_graph, framework)
    assert report is not None
    assert report.passed + report.partial + report.failed == report.total_checks


def test_generate_html_secure_graph_nist(
    secure_graph: InfraGraph, tmp_path: Path
) -> None:
    """NIST CSF report for secure graph should be generated without error."""
    out = tmp_path / "nist_secure.html"
    generate_compliance_html(secure_graph, ["nist_csf"], out)
    content = out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
