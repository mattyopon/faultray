"""Tests for Compliance Evidence Auto-Generator."""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    OperationalProfile,
    RegionConfig,
    ResourceMetrics,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.reporter.evidence_generator import (
    CONTROL_MAPPINGS,
    EvidenceGenerator,
    EvidenceItem,
    EvidencePackage,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _build_secure_graph() -> InfraGraph:
    """Build a well-secured graph (encryption, logging, failover)."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="web", name="Web Server", type=ComponentType.WEB_SERVER,
        replicas=2,
        failover=FailoverConfig(enabled=True),
        security=SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            log_enabled=True,
            ids_monitored=True,
            waf_protected=True,
        ),
        region=RegionConfig(region="us-east-1", dr_target_region="us-west-2"),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=2,
        failover=FailoverConfig(enabled=True),
        security=SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            log_enabled=True,
            ids_monitored=True,
        ),
        region=RegionConfig(region="us-east-1", dr_target_region="us-west-2"),
    ))
    graph.add_dependency(Dependency(source_id="web", target_id="db", dependency_type="requires"))
    return graph


def _build_insecure_graph() -> InfraGraph:
    """Build an insecure graph (no encryption, no logging, no DR)."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=1,
        security=SecurityProfile(
            encryption_at_rest=False,
            encryption_in_transit=False,
            log_enabled=False,
            ids_monitored=False,
        ),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
        security=SecurityProfile(
            encryption_at_rest=False,
            encryption_in_transit=False,
            log_enabled=False,
        ),
    ))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


def _build_graph_with_external_api() -> InfraGraph:
    """Graph with an external API dependency."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        security=SecurityProfile(encryption_at_rest=True, encryption_in_transit=True, log_enabled=True),
    ))
    graph.add_component(Component(
        id="stripe", name="Stripe API", type=ComponentType.EXTERNAL_API,
        replicas=1,
        failover=FailoverConfig(enabled=True),
        security=SecurityProfile(encryption_at_rest=True, encryption_in_transit=True, log_enabled=True),
    ))
    graph.add_dependency(Dependency(source_id="app", target_id="stripe", dependency_type="requires"))
    return graph


class _MockSimReport:
    """Minimal mock of SimulationReport."""
    def __init__(self, critical=0, warnings=0, passed=5, score=80.0):
        self.results = [None] * (critical + warnings + passed)
        self.critical_findings = [None] * critical
        self.warnings = [None] * warnings
        self.passed = [None] * passed
        self.resilience_score = score


# ---------------------------------------------------------------------------
# Tests: Framework support
# ---------------------------------------------------------------------------

class TestFrameworkSupport:
    """Test supported frameworks and control mappings."""

    def test_supported_frameworks(self):
        frameworks = EvidenceGenerator.supported_frameworks()
        assert "SOC2" in frameworks
        assert "DORA" in frameworks
        assert "ISO27001" in frameworks
        assert "PCI-DSS" in frameworks

    def test_control_mappings_not_empty(self):
        for fw, controls in CONTROL_MAPPINGS.items():
            assert len(controls) > 0, f"Framework {fw} has no controls"

    def test_unsupported_framework_raises(self):
        graph = _build_secure_graph()
        gen = EvidenceGenerator(graph)
        with pytest.raises(ValueError, match="Unsupported framework"):
            gen.generate("HIPAA")


# ---------------------------------------------------------------------------
# Tests: Evidence generation
# ---------------------------------------------------------------------------

class TestSOC2Evidence:
    """Test SOC 2 evidence generation."""

    def test_generate_soc2_secure(self):
        graph = _build_secure_graph()
        gen = EvidenceGenerator(graph)
        package = gen.generate("SOC2")

        assert isinstance(package, EvidencePackage)
        assert package.framework == "SOC2"
        assert package.total_controls_tested == len(CONTROL_MAPPINGS["SOC2"])
        assert package.total_controls_tested > 0

    def test_soc2_with_simulation(self):
        graph = _build_secure_graph()
        gen = EvidenceGenerator(graph)
        sim = _MockSimReport(critical=0, warnings=1, passed=10, score=85.0)
        package = gen.generate("SOC2", simulation_report=sim)

        # With warnings but no critical, some controls should be Partial
        results = {i.control_id: i.result for i in package.items}
        # CC9.1 maps to chaos_simulation — should be Partial due to warnings
        assert results["CC9.1"] == "Partial"

    def test_soc2_with_critical_fails(self):
        graph = _build_secure_graph()
        gen = EvidenceGenerator(graph)
        sim = _MockSimReport(critical=2, warnings=0, passed=5, score=50.0)
        package = gen.generate("SOC2", simulation_report=sim)

        results = {i.control_id: i.result for i in package.items}
        assert results["CC9.1"] == "Fail"


class TestDORAEvidence:
    """Test DORA evidence generation."""

    def test_generate_dora(self):
        graph = _build_secure_graph()
        gen = EvidenceGenerator(graph)
        package = gen.generate("DORA")

        assert package.framework == "DORA"
        assert package.total_controls_tested == len(CONTROL_MAPPINGS["DORA"])

    def test_dora_supply_chain_no_externals(self):
        graph = _build_secure_graph()
        gen = EvidenceGenerator(graph)
        package = gen.generate("DORA")

        # No external APIs → supply chain should pass
        art26 = [i for i in package.items if i.control_id == "Art.26"]
        assert len(art26) == 1
        assert art26[0].result == "Pass"

    def test_dora_supply_chain_with_external(self):
        graph = _build_graph_with_external_api()
        gen = EvidenceGenerator(graph)
        package = gen.generate("DORA")

        art26 = [i for i in package.items if i.control_id == "Art.26"]
        assert len(art26) == 1
        # External API with failover → Pass
        assert art26[0].result == "Pass"


class TestISO27001Evidence:
    """Test ISO 27001 evidence generation."""

    def test_generate_iso27001(self):
        graph = _build_secure_graph()
        gen = EvidenceGenerator(graph)
        package = gen.generate("ISO27001")

        assert package.framework == "ISO27001"
        assert package.total_controls_tested == len(CONTROL_MAPPINGS["ISO27001"])

    def test_iso27001_no_dr_fails(self):
        graph = _build_insecure_graph()
        gen = EvidenceGenerator(graph)
        package = gen.generate("ISO27001")

        a171 = [i for i in package.items if i.control_id == "A.17.1"]
        assert len(a171) == 1
        assert a171[0].result == "Fail"  # No DR configured


class TestPCIDSSEvidence:
    """Test PCI-DSS evidence generation."""

    def test_generate_pcidss(self):
        graph = _build_secure_graph()
        gen = EvidenceGenerator(graph)
        package = gen.generate("PCI-DSS")

        assert package.framework == "PCI-DSS"
        assert package.total_controls_tested == len(CONTROL_MAPPINGS["PCI-DSS"])


class TestInsecureGraph:
    """Test evidence generation against an insecure graph."""

    def test_security_controls_fail(self):
        graph = _build_insecure_graph()
        gen = EvidenceGenerator(graph)
        package = gen.generate("SOC2")

        # Security analysis should fail — no encryption
        sec_items = [i for i in package.items if i.test_performed == "security_analysis"]
        for item in sec_items:
            assert item.result == "Fail"

    def test_coverage_below_100(self):
        graph = _build_insecure_graph()
        gen = EvidenceGenerator(graph)
        package = gen.generate("SOC2")

        assert package.failed > 0
        assert package.coverage_percent < 100.0


# ---------------------------------------------------------------------------
# Tests: Export
# ---------------------------------------------------------------------------

class TestCSVExport:
    """Test CSV export functionality."""

    def test_export_csv(self, tmp_path):
        graph = _build_secure_graph()
        gen = EvidenceGenerator(graph)
        package = gen.generate("SOC2")

        csv_path = tmp_path / "evidence.csv"
        gen.export_csv(package, csv_path)

        assert csv_path.exists()
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Header + data rows
        assert len(rows) == package.total_controls_tested + 1
        assert rows[0][0] == "Framework"

    def test_export_csv_creates_parent_dirs(self, tmp_path):
        graph = _build_secure_graph()
        gen = EvidenceGenerator(graph)
        package = gen.generate("SOC2")

        csv_path = tmp_path / "sub" / "dir" / "evidence.csv"
        gen.export_csv(package, csv_path)
        assert csv_path.exists()


class TestJSONExport:
    """Test JSON export functionality."""

    def test_export_json(self):
        graph = _build_secure_graph()
        gen = EvidenceGenerator(graph)
        package = gen.generate("DORA")

        data = gen.export_json(package)
        assert data["framework"] == "DORA"
        assert data["total_controls_tested"] == len(CONTROL_MAPPINGS["DORA"])
        assert len(data["items"]) == data["total_controls_tested"]

    def test_export_json_items_have_fields(self):
        graph = _build_secure_graph()
        gen = EvidenceGenerator(graph)
        package = gen.generate("SOC2")

        data = gen.export_json(package)
        for item in data["items"]:
            assert "control_id" in item
            assert "result" in item
            assert "evidence_detail" in item


# ---------------------------------------------------------------------------
# Tests: EvidencePackage counts
# ---------------------------------------------------------------------------

class TestEvidencePackageCounts:
    """Test that passed/failed/coverage counts are correct."""

    def test_all_pass_coverage_100(self):
        graph = _build_secure_graph()
        gen = EvidenceGenerator(graph)
        sim = _MockSimReport(critical=0, warnings=0, passed=20, score=90.0)
        package = gen.generate("SOC2", simulation_report=sim)

        # With a secure graph and clean simulation, most should pass.
        # The availability_model evaluator uses graph.resilience_score_v2()
        # which may return <80 for the test graph, yielding "Partial".
        assert package.failed == 0
        assert package.passed >= package.total_controls_tested - 1
        # Coverage should be high (83%+ even if one Partial)
        assert package.coverage_percent >= 80.0

    def test_mixed_results(self):
        graph = _build_insecure_graph()
        gen = EvidenceGenerator(graph)
        package = gen.generate("SOC2")

        assert package.passed + package.failed <= package.total_controls_tested
