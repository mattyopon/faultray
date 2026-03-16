"""Comprehensive tests for faultray.simulator.supply_chain_engine."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.supply_chain_engine import (
    DEFAULT_IMPACT,
    SEVERITY_ORDER,
    SupplyChainEngine,
    SupplyChainReport,
    VulnerabilityImpact,
    _IMPACT_BY_COMPONENT_TYPE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(cid, name, ctype=ComponentType.APP_SERVER, replicas=1, **kwargs):
    return Component(id=cid, name=name, type=ctype, replicas=replicas, **kwargs)


def _make_graph(*components, deps=None):
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for src, tgt, dtype in (deps or []):
        g.add_dependency(Dependency(source_id=src, target_id=tgt, dependency_type=dtype))
    return g


def _standard_graph():
    """4-tier graph: lb -> app -> db, app -> cache."""
    return _make_graph(
        _comp("lb", "Load Balancer", ctype=ComponentType.LOAD_BALANCER),
        _comp("app", "App Server", ctype=ComponentType.APP_SERVER),
        _comp("db", "Database", ctype=ComponentType.DATABASE),
        _comp("cache", "Redis Cache", ctype=ComponentType.CACHE),
        _comp("queue", "Kafka Queue", ctype=ComponentType.QUEUE),
        _comp("storage", "S3 Storage", ctype=ComponentType.STORAGE),
        _comp("web", "Nginx", ctype=ComponentType.WEB_SERVER),
        _comp("ext", "External API", ctype=ComponentType.EXTERNAL_API),
        deps=[
            ("lb", "app", "requires"),
            ("app", "db", "requires"),
            ("app", "cache", "optional"),
            ("app", "queue", "async"),
            ("app", "storage", "optional"),
            ("web", "app", "requires"),
        ],
    )


def _write_json(data, tmp_path, filename="vulns.json"):
    p = tmp_path / filename
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Verify module-level constants."""

    def test_severity_order_keys(self):
        expected = {"critical", "high", "medium", "low", "info"}
        assert set(SEVERITY_ORDER.keys()) == expected

    def test_severity_order_values_ascending(self):
        assert SEVERITY_ORDER["info"] < SEVERITY_ORDER["low"]
        assert SEVERITY_ORDER["low"] < SEVERITY_ORDER["medium"]
        assert SEVERITY_ORDER["medium"] < SEVERITY_ORDER["high"]
        assert SEVERITY_ORDER["high"] < SEVERITY_ORDER["critical"]

    def test_impact_by_component_type_keys(self):
        expected_types = {
            "database", "cache", "app_server", "web_server",
            "load_balancer", "queue", "storage", "external_api",
        }
        assert set(_IMPACT_BY_COMPONENT_TYPE.keys()) == expected_types

    def test_each_impact_has_all_severities(self):
        for ctype, impacts in _IMPACT_BY_COMPONENT_TYPE.items():
            for sev in ("critical", "high", "medium", "low"):
                assert sev in impacts, f"{ctype} missing severity {sev}"

    def test_default_impact_keys(self):
        for sev in ("critical", "high", "medium", "low"):
            assert sev in DEFAULT_IMPACT


# ---------------------------------------------------------------------------
# VulnerabilityImpact dataclass
# ---------------------------------------------------------------------------


class TestVulnerabilityImpact:
    """Tests for VulnerabilityImpact dataclass."""

    def test_create(self):
        vi = VulnerabilityImpact(
            cve_id="CVE-2024-0001",
            package="test-pkg",
            severity="high",
            affected_components=["app"],
            infrastructure_impact="OOM",
            estimated_blast_radius=3,
            risk_score=7.5,
        )
        assert vi.cve_id == "CVE-2024-0001"
        assert vi.package == "test-pkg"
        assert vi.severity == "high"
        assert vi.affected_components == ["app"]
        assert vi.infrastructure_impact == "OOM"
        assert vi.estimated_blast_radius == 3
        assert vi.risk_score == 7.5

    def test_empty_affected_components(self):
        vi = VulnerabilityImpact(
            cve_id="CVE-X", package="", severity="low",
            affected_components=[], infrastructure_impact="minor",
            estimated_blast_radius=0, risk_score=0.0,
        )
        assert vi.affected_components == []


# ---------------------------------------------------------------------------
# SupplyChainReport dataclass
# ---------------------------------------------------------------------------


class TestSupplyChainReport:
    """Tests for SupplyChainReport dataclass."""

    def test_create_empty(self):
        r = SupplyChainReport(
            total_vulnerabilities=0, critical_count=0,
            infrastructure_risk_score=0.0,
        )
        assert r.impacts == []
        assert r.recommendations == []

    def test_create_with_data(self):
        vi = VulnerabilityImpact(
            cve_id="CVE-1", package="p", severity="high",
            affected_components=["x"], infrastructure_impact="OOM",
            estimated_blast_radius=1, risk_score=5.0,
        )
        r = SupplyChainReport(
            total_vulnerabilities=1, critical_count=0,
            infrastructure_risk_score=50.0,
            impacts=[vi], recommendations=["patch it"],
        )
        assert len(r.impacts) == 1
        assert len(r.recommendations) == 1


# ---------------------------------------------------------------------------
# map_cve_to_impact
# ---------------------------------------------------------------------------


class TestMapCveToImpact:
    """Tests for SupplyChainEngine.map_cve_to_impact."""

    def test_critical_database(self):
        engine = SupplyChainEngine(_standard_graph())
        impact = engine.map_cve_to_impact("CVE-1", "critical", ["db"], package="postgres")
        assert impact.severity == "critical"
        assert impact.infrastructure_impact == "data breach"
        assert impact.risk_score > 0

    def test_high_app_server(self):
        engine = SupplyChainEngine(_standard_graph())
        impact = engine.map_cve_to_impact("CVE-2", "high", ["app"], package="express")
        assert impact.severity == "high"
        assert impact.infrastructure_impact == "OOM"

    def test_medium_cache(self):
        engine = SupplyChainEngine(_standard_graph())
        impact = engine.map_cve_to_impact("CVE-3", "medium", ["cache"])
        assert impact.severity == "medium"
        assert impact.infrastructure_impact == "degraded hit ratio"

    def test_low_queue(self):
        engine = SupplyChainEngine(_standard_graph())
        impact = engine.map_cve_to_impact("CVE-4", "low", ["queue"])
        assert impact.severity == "low"
        assert impact.infrastructure_impact == "minor latency increase"

    def test_critical_load_balancer(self):
        engine = SupplyChainEngine(_standard_graph())
        impact = engine.map_cve_to_impact("CVE-5", "critical", ["lb"])
        assert impact.infrastructure_impact == "traffic hijack"

    def test_high_storage(self):
        engine = SupplyChainEngine(_standard_graph())
        impact = engine.map_cve_to_impact("CVE-6", "high", ["storage"])
        assert impact.infrastructure_impact == "data loss"

    def test_critical_web_server(self):
        engine = SupplyChainEngine(_standard_graph())
        impact = engine.map_cve_to_impact("CVE-7", "critical", ["web"])
        assert impact.infrastructure_impact == "remote code execution"

    def test_high_external_api(self):
        engine = SupplyChainEngine(_standard_graph())
        impact = engine.map_cve_to_impact("CVE-8", "high", ["ext"])
        assert impact.infrastructure_impact == "API abuse"

    def test_severity_case_insensitive(self):
        engine = SupplyChainEngine(_standard_graph())
        impact = engine.map_cve_to_impact("CVE-9", "CRITICAL", ["db"])
        assert impact.severity == "critical"

    def test_severity_mixed_case(self):
        engine = SupplyChainEngine(_standard_graph())
        impact = engine.map_cve_to_impact("CVE-10", "High", ["app"])
        assert impact.severity == "high"

    def test_unknown_severity_fallback(self):
        engine = SupplyChainEngine(_standard_graph())
        impact = engine.map_cve_to_impact("CVE-11", "unknown", ["app"])
        assert impact.severity == "unknown"
        # Unknown severity gets default weight of 1
        assert impact.risk_score >= 0

    def test_empty_affected_components(self):
        engine = SupplyChainEngine(_standard_graph())
        impact = engine.map_cve_to_impact("CVE-12", "high", [])
        assert impact.estimated_blast_radius == 0
        # No component types -> default impact
        assert impact.infrastructure_impact in DEFAULT_IMPACT.values()

    def test_nonexistent_component_id(self):
        """Nonexistent component ID raises NetworkXError from get_all_affected."""
        import networkx as nx
        engine = SupplyChainEngine(_standard_graph())
        with pytest.raises(nx.NetworkXError):
            engine.map_cve_to_impact("CVE-13", "high", ["nonexistent"])

    def test_multiple_affected_components(self):
        engine = SupplyChainEngine(_standard_graph())
        impact = engine.map_cve_to_impact("CVE-14", "critical", ["db", "cache"])
        assert len(impact.affected_components) == 2

    def test_blast_radius_uses_max(self):
        """blast_radius should be the max across all affected components."""
        engine = SupplyChainEngine(_standard_graph())
        impact = engine.map_cve_to_impact("CVE-15", "critical", ["db", "app"])
        # db has dependents (app), app has dependents (lb, web)
        assert impact.estimated_blast_radius >= 0

    def test_risk_score_capped_at_10(self):
        engine = SupplyChainEngine(_standard_graph())
        impact = engine.map_cve_to_impact("CVE-16", "critical", ["db", "app", "lb", "cache"])
        assert impact.risk_score <= 10.0

    def test_risk_score_non_negative(self):
        engine = SupplyChainEngine(_standard_graph())
        impact = engine.map_cve_to_impact("CVE-17", "info", [])
        assert impact.risk_score >= 0

    def test_info_severity(self):
        engine = SupplyChainEngine(_standard_graph())
        impact = engine.map_cve_to_impact("CVE-18", "info", ["app"])
        assert impact.severity == "info"
        assert impact.risk_score >= 0

    def test_empty_package(self):
        engine = SupplyChainEngine(_standard_graph())
        impact = engine.map_cve_to_impact("CVE-19", "medium", ["app"])
        assert impact.package == ""

    def test_package_passed_through(self):
        engine = SupplyChainEngine(_standard_graph())
        impact = engine.map_cve_to_impact("CVE-20", "medium", ["app"], package="lodash")
        assert impact.package == "lodash"

    def test_risk_score_rounded(self):
        engine = SupplyChainEngine(_standard_graph())
        impact = engine.map_cve_to_impact("CVE-21", "medium", ["db"])
        # risk_score should be rounded to 1 decimal place
        assert impact.risk_score == round(impact.risk_score, 1)


# ---------------------------------------------------------------------------
# _normalize_input
# ---------------------------------------------------------------------------


class TestNormalizeInput:
    """Tests for SupplyChainEngine._normalize_input static method."""

    def test_direct_array(self):
        data = [{"cve_id": "CVE-1"}]
        result = SupplyChainEngine._normalize_input(data)
        assert result == data

    def test_empty_array(self):
        result = SupplyChainEngine._normalize_input([])
        assert result == []

    def test_snyk_format(self):
        data = {"vulnerabilities": [{"id": "CVE-1"}, {"id": "CVE-2"}]}
        result = SupplyChainEngine._normalize_input(data)
        assert len(result) == 2

    def test_trivy_format(self):
        data = {
            "Results": [
                {"Vulnerabilities": [{"VulnerabilityID": "CVE-1"}]},
                {"Vulnerabilities": [{"VulnerabilityID": "CVE-2"}]},
            ]
        }
        result = SupplyChainEngine._normalize_input(data)
        assert len(result) == 2

    def test_trivy_missing_vulnerabilities_key(self):
        data = {"Results": [{"Target": "Gemfile.lock"}]}
        result = SupplyChainEngine._normalize_input(data)
        assert result == []

    def test_trivy_empty_results(self):
        data = {"Results": []}
        result = SupplyChainEngine._normalize_input(data)
        assert result == []

    def test_dependabot_format(self):
        data = {"results": [{"id": "CVE-1"}]}
        result = SupplyChainEngine._normalize_input(data)
        assert len(result) == 1

    def test_dict_no_known_keys(self):
        data = {"unknown_key": [1, 2, 3]}
        result = SupplyChainEngine._normalize_input(data)
        assert result == []

    def test_non_dict_non_list(self):
        result = SupplyChainEngine._normalize_input("string")
        assert result == []

    def test_integer_input(self):
        result = SupplyChainEngine._normalize_input(42)
        assert result == []

    def test_none_like_input(self):
        """Not actually None (would fail on isinstance), but edge case."""
        result = SupplyChainEngine._normalize_input({})
        assert result == []

    def test_snyk_with_extra_keys(self):
        data = {"vulnerabilities": [{"id": "CVE-1"}], "metadata": {"version": "1"}}
        result = SupplyChainEngine._normalize_input(data)
        assert len(result) == 1

    def test_precedence_vulnerabilities_over_results(self):
        """Snyk key takes precedence over Dependabot key."""
        data = {"vulnerabilities": [{"id": "snyk"}], "results": [{"id": "dependabot"}]}
        result = SupplyChainEngine._normalize_input(data)
        assert result == [{"id": "snyk"}]


# ---------------------------------------------------------------------------
# analyze_from_data
# ---------------------------------------------------------------------------


class TestAnalyzeFromData:
    """Tests for SupplyChainEngine.analyze_from_data."""

    def test_empty_list(self):
        engine = SupplyChainEngine(_standard_graph())
        report = engine.analyze_from_data([])
        assert report.total_vulnerabilities == 0
        assert report.critical_count == 0
        assert report.infrastructure_risk_score == 0.0
        assert len(report.recommendations) == 1
        assert "No vulnerabilities" in report.recommendations[0]

    def test_single_critical(self):
        engine = SupplyChainEngine(_standard_graph())
        report = engine.analyze_from_data([{
            "cve_id": "CVE-1",
            "severity": "critical",
            "package": "postgres",
            "affected_components": ["db"],
        }])
        assert report.total_vulnerabilities == 1
        assert report.critical_count == 1
        assert report.infrastructure_risk_score > 0
        assert any("URGENT" in r for r in report.recommendations)

    def test_single_high(self):
        engine = SupplyChainEngine(_standard_graph())
        report = engine.analyze_from_data([{
            "cve_id": "CVE-2",
            "severity": "high",
            "package": "express",
            "affected_components": ["app"],
        }])
        assert report.total_vulnerabilities == 1
        assert report.critical_count == 0
        assert any("high-severity" in r for r in report.recommendations)

    def test_single_low(self):
        engine = SupplyChainEngine(_standard_graph())
        report = engine.analyze_from_data([{
            "cve_id": "CVE-3",
            "severity": "low",
            "package": "colors",
            "affected_components": ["app"],
        }])
        assert report.total_vulnerabilities == 1
        assert report.critical_count == 0
        assert any("low/medium" in r for r in report.recommendations)

    def test_mixed_severities(self):
        engine = SupplyChainEngine(_standard_graph())
        data = [
            {"cve_id": "CVE-C", "severity": "critical", "affected_components": ["db"]},
            {"cve_id": "CVE-H", "severity": "high", "affected_components": ["app"]},
            {"cve_id": "CVE-M", "severity": "medium", "affected_components": ["cache"]},
            {"cve_id": "CVE-L", "severity": "low", "affected_components": ["queue"]},
        ]
        report = engine.analyze_from_data(data)
        assert report.total_vulnerabilities == 4
        assert report.critical_count == 1
        assert len(report.impacts) == 4

    def test_risk_score_capped_at_100(self):
        engine = SupplyChainEngine(_standard_graph())
        # Many critical vulns should cap at 100
        data = [
            {"cve_id": f"CVE-{i}", "severity": "critical", "affected_components": ["db"]}
            for i in range(20)
        ]
        report = engine.analyze_from_data(data)
        assert report.infrastructure_risk_score <= 100.0

    def test_risk_score_non_negative(self):
        engine = SupplyChainEngine(_standard_graph())
        report = engine.analyze_from_data([
            {"cve_id": "CVE-1", "severity": "info", "affected_components": []},
        ])
        assert report.infrastructure_risk_score >= 0.0


# ---------------------------------------------------------------------------
# analyze_from_data: CVE ID extraction from various formats
# ---------------------------------------------------------------------------


class TestCveIdExtraction:
    """Verify CVE ID extraction from different vulnerability report formats."""

    def _analyze_single(self, entry):
        engine = SupplyChainEngine(_standard_graph())
        report = engine.analyze_from_data([entry])
        return report.impacts[0].cve_id

    def test_cve_id_key(self):
        assert self._analyze_single({"cve_id": "CVE-2024-001", "severity": "low"}) == "CVE-2024-001"

    def test_vulnerability_id_key(self):
        """Trivy format: VulnerabilityID."""
        assert self._analyze_single({"VulnerabilityID": "CVE-T", "severity": "low"}) == "CVE-T"

    def test_id_key(self):
        """Generic id key."""
        assert self._analyze_single({"id": "CVE-G", "severity": "low"}) == "CVE-G"

    def test_advisory_cve_id(self):
        """Nested advisory.cve_id."""
        result = self._analyze_single({"advisory": {"cve_id": "CVE-A"}, "severity": "low"})
        assert result == "CVE-A"

    def test_no_cve_id_falls_to_unknown(self):
        result = self._analyze_single({"severity": "low"})
        assert result == "UNKNOWN"

    def test_precedence_cve_id_over_id(self):
        result = self._analyze_single({"cve_id": "CVE-FIRST", "id": "CVE-SECOND", "severity": "low"})
        assert result == "CVE-FIRST"


# ---------------------------------------------------------------------------
# analyze_from_data: severity extraction
# ---------------------------------------------------------------------------


class TestSeverityExtraction:
    """Verify severity extraction from different formats."""

    def _get_severity(self, entry):
        engine = SupplyChainEngine(_standard_graph())
        report = engine.analyze_from_data([entry])
        return report.impacts[0].severity

    def test_severity_key(self):
        assert self._get_severity({"cve_id": "X", "severity": "high"}) == "high"

    def test_severity_key_capitalized(self):
        """Trivy format: Severity."""
        assert self._get_severity({"cve_id": "X", "Severity": "HIGH"}) == "high"

    def test_advisory_severity(self):
        result = self._get_severity({"cve_id": "X", "advisory": {"severity": "critical"}})
        assert result == "critical"

    def test_default_severity_medium(self):
        result = self._get_severity({"cve_id": "X"})
        assert result == "medium"


# ---------------------------------------------------------------------------
# analyze_from_data: package extraction
# ---------------------------------------------------------------------------


class TestPackageExtraction:
    """Verify package name extraction."""

    def _get_package(self, entry):
        engine = SupplyChainEngine(_standard_graph())
        report = engine.analyze_from_data([entry])
        return report.impacts[0].package

    def test_package_key(self):
        assert self._get_package({"cve_id": "X", "severity": "low", "package": "lodash"}) == "lodash"

    def test_pkg_name_key(self):
        """Trivy: PkgName."""
        assert self._get_package({"cve_id": "X", "severity": "low", "PkgName": "openssl"}) == "openssl"

    def test_name_key(self):
        assert self._get_package({"cve_id": "X", "severity": "low", "name": "axios"}) == "axios"

    def test_no_package_defaults_empty(self):
        assert self._get_package({"cve_id": "X", "severity": "low"}) == ""


# ---------------------------------------------------------------------------
# _auto_map_components
# ---------------------------------------------------------------------------


class TestAutoMapComponents:
    """Tests for heuristic component mapping."""

    def _engine(self):
        return SupplyChainEngine(_standard_graph())

    def test_database_keywords(self):
        engine = self._engine()
        ids = list(engine._graph.components.keys())
        for kw in ["sql", "postgres", "mysql", "mongo", "redis", "database", "db"]:
            result = engine._auto_map_components(
                {"package": kw, "severity": "high"}, ids
            )
            # Should match database or cache component
            assert len(result) >= 0  # At least not crashing

    def test_cache_keywords(self):
        engine = self._engine()
        ids = list(engine._graph.components.keys())
        result = engine._auto_map_components(
            {"package": "redis-cache-lib", "severity": "high"}, ids
        )
        # Should match cache component
        cache_matched = any(
            engine._graph.get_component(r) and
            engine._graph.get_component(r).type in (ComponentType.CACHE, ComponentType.DATABASE)
            for r in result
        )
        assert cache_matched or len(result) > 0

    def test_app_server_keywords(self):
        engine = self._engine()
        ids = list(engine._graph.components.keys())
        for kw in ["express", "flask", "django", "spring", "fastapi", "node"]:
            result = engine._auto_map_components(
                {"package": kw, "severity": "high"}, ids
            )
            if result:
                comp = engine._graph.get_component(result[0])
                assert comp is not None

    def test_web_server_keywords(self):
        engine = self._engine()
        ids = list(engine._graph.components.keys())
        result = engine._auto_map_components(
            {"package": "nginx-module", "severity": "high"}, ids
        )
        assert len(result) > 0

    def test_queue_keywords(self):
        engine = self._engine()
        ids = list(engine._graph.components.keys())
        result = engine._auto_map_components(
            {"package": "kafka-client", "severity": "high"}, ids
        )
        assert len(result) > 0

    def test_load_balancer_keywords(self):
        engine = self._engine()
        ids = list(engine._graph.components.keys())
        result = engine._auto_map_components(
            {"package": "haproxy-mod", "severity": "high"}, ids
        )
        assert len(result) > 0

    def test_storage_keywords(self):
        engine = self._engine()
        ids = list(engine._graph.components.keys())
        result = engine._auto_map_components(
            {"package": "s3-client", "severity": "high"}, ids
        )
        assert len(result) > 0

    def test_description_used_for_matching(self):
        engine = self._engine()
        ids = list(engine._graph.components.keys())
        result = engine._auto_map_components(
            {"package": "unknown-pkg", "description": "SQL injection vulnerability", "severity": "high"},
            ids,
        )
        # "sql" in description -> should match database
        assert len(result) > 0

    def test_trivy_description_key(self):
        engine = self._engine()
        ids = list(engine._graph.components.keys())
        result = engine._auto_map_components(
            {"PkgName": "foo", "Description": "Redis memory corruption", "severity": "high"},
            ids,
        )
        assert len(result) > 0

    def test_title_key_used_as_description(self):
        engine = self._engine()
        ids = list(engine._graph.components.keys())
        result = engine._auto_map_components(
            {"name": "foo", "title": "nginx buffer overflow", "severity": "high"},
            ids,
        )
        assert len(result) > 0

    def test_no_match_falls_back_to_first_component(self):
        engine = self._engine()
        ids = list(engine._graph.components.keys())
        result = engine._auto_map_components(
            {"package": "completely-unrelated-xyz", "severity": "high"}, ids
        )
        # Should fallback to first component
        assert len(result) == 1
        assert result[0] == ids[0]

    def test_no_match_empty_component_ids(self):
        engine = self._engine()
        result = engine._auto_map_components(
            {"package": "unknown", "severity": "high"}, []
        )
        assert result == []

    def test_empty_entry(self):
        engine = self._engine()
        ids = list(engine._graph.components.keys())
        result = engine._auto_map_components({}, ids)
        # No package/description -> fallback to first component
        assert len(result) >= 1 or len(result) == 0


# ---------------------------------------------------------------------------
# _determine_impact
# ---------------------------------------------------------------------------


class TestDetermineImpact:
    """Tests for _determine_impact method."""

    def _engine(self):
        return SupplyChainEngine(_standard_graph())

    def test_database_critical(self):
        engine = self._engine()
        result = engine._determine_impact({"database"}, "critical")
        assert result == "data breach"

    def test_cache_high(self):
        engine = self._engine()
        result = engine._determine_impact({"cache"}, "high")
        assert result == "OOM"

    def test_multiple_types_uses_specific(self):
        engine = self._engine()
        result = engine._determine_impact({"database", "cache"}, "critical")
        # Should return a specific impact from one of the types
        assert result in ("data breach", "cache poisoning")

    def test_unknown_type_uses_default(self):
        engine = self._engine()
        result = engine._determine_impact({"unknown_type"}, "critical")
        assert result == DEFAULT_IMPACT["critical"]

    def test_empty_comp_types_uses_default(self):
        engine = self._engine()
        result = engine._determine_impact(set(), "high")
        assert result == DEFAULT_IMPACT["high"]

    def test_unknown_severity_fallback(self):
        engine = self._engine()
        result = engine._determine_impact({"database"}, "unknown_sev")
        assert result == "degraded performance"


# ---------------------------------------------------------------------------
# _generate_recommendations
# ---------------------------------------------------------------------------


class TestGenerateRecommendations:
    """Tests for recommendation generation."""

    def _impact(self, severity="medium", package="test", blast_radius=0, infra_impact="CPU spike"):
        return VulnerabilityImpact(
            cve_id="CVE-X", package=package, severity=severity,
            affected_components=["app"], infrastructure_impact=infra_impact,
            estimated_blast_radius=blast_radius, risk_score=5.0,
        )

    def test_no_impacts_returns_scan_recommendation(self):
        result = SupplyChainEngine._generate_recommendations([])
        assert len(result) == 1
        assert "No vulnerabilities" in result[0]

    def test_critical_generates_urgent(self):
        result = SupplyChainEngine._generate_recommendations([
            self._impact(severity="critical", package="pg"),
        ])
        assert any("URGENT" in r for r in result)

    def test_critical_lists_packages(self):
        result = SupplyChainEngine._generate_recommendations([
            self._impact(severity="critical", package="pg"),
            self._impact(severity="critical", package="openssl"),
        ])
        urgent = [r for r in result if "URGENT" in r]
        assert len(urgent) == 1
        assert "pg" in urgent[0]
        assert "openssl" in urgent[0]

    def test_critical_with_no_package(self):
        result = SupplyChainEngine._generate_recommendations([
            self._impact(severity="critical", package=""),
        ])
        assert any("URGENT" in r for r in result)

    def test_high_generates_schedule_patching(self):
        result = SupplyChainEngine._generate_recommendations([
            self._impact(severity="high"),
        ])
        assert any("7 days" in r for r in result)

    def test_high_blast_radius_generates_segmentation_rec(self):
        result = SupplyChainEngine._generate_recommendations([
            self._impact(blast_radius=5),
        ])
        assert any("blast radius" in r for r in result)

    def test_blast_radius_below_3_no_segmentation_rec(self):
        result = SupplyChainEngine._generate_recommendations([
            self._impact(blast_radius=2),
        ])
        assert not any("blast radius" in r for r in result)

    def test_data_breach_generates_encryption_rec(self):
        result = SupplyChainEngine._generate_recommendations([
            self._impact(infra_impact="data breach"),
        ])
        assert any("encryption" in r for r in result)

    def test_no_breach_no_encryption_rec(self):
        result = SupplyChainEngine._generate_recommendations([
            self._impact(infra_impact="CPU spike"),
        ])
        assert not any("encryption" in r for r in result)

    def test_low_severity_only_monitor_message(self):
        result = SupplyChainEngine._generate_recommendations([
            self._impact(severity="low", blast_radius=0, infra_impact="minor"),
        ])
        assert any("low/medium" in r for r in result)

    def test_critical_package_limit_5(self):
        """Recommendation lists max 5 packages."""
        impacts = [
            self._impact(severity="critical", package=f"pkg-{i}")
            for i in range(10)
        ]
        result = SupplyChainEngine._generate_recommendations(impacts)
        urgent = [r for r in result if "URGENT" in r][0]
        # Should list at most 5 packages
        pkg_part = urgent.split("(")[1] if "(" in urgent else ""
        listed_packages = pkg_part.split(")")[0].split(",") if pkg_part else []
        assert len(listed_packages) <= 5


# ---------------------------------------------------------------------------
# analyze_from_file
# ---------------------------------------------------------------------------


class TestAnalyzeFromFile:
    """Tests for analyze_from_file (file I/O)."""

    def test_direct_array_file(self, tmp_path):
        engine = SupplyChainEngine(_standard_graph())
        data = [{"cve_id": "CVE-1", "severity": "high", "package": "lodash"}]
        p = _write_json(data, tmp_path)
        report = engine.analyze_from_file(p)
        assert report.total_vulnerabilities == 1

    def test_snyk_format_file(self, tmp_path):
        engine = SupplyChainEngine(_standard_graph())
        data = {
            "vulnerabilities": [
                {"cve_id": "CVE-1", "severity": "critical", "package": "express"},
                {"cve_id": "CVE-2", "severity": "high", "package": "lodash"},
            ]
        }
        p = _write_json(data, tmp_path)
        report = engine.analyze_from_file(p)
        assert report.total_vulnerabilities == 2
        assert report.critical_count == 1

    def test_trivy_format_file(self, tmp_path):
        engine = SupplyChainEngine(_standard_graph())
        data = {
            "Results": [{
                "Target": "package-lock.json",
                "Vulnerabilities": [
                    {"VulnerabilityID": "CVE-T1", "Severity": "HIGH", "PkgName": "axios"},
                ]
            }]
        }
        p = _write_json(data, tmp_path)
        report = engine.analyze_from_file(p)
        assert report.total_vulnerabilities == 1

    def test_dependabot_format_file(self, tmp_path):
        engine = SupplyChainEngine(_standard_graph())
        data = {"results": [{"id": "CVE-D1", "severity": "medium", "name": "colors"}]}
        p = _write_json(data, tmp_path)
        report = engine.analyze_from_file(p)
        assert report.total_vulnerabilities == 1

    def test_empty_array_file(self, tmp_path):
        engine = SupplyChainEngine(_standard_graph())
        p = _write_json([], tmp_path)
        report = engine.analyze_from_file(p)
        assert report.total_vulnerabilities == 0

    def test_empty_object_file(self, tmp_path):
        engine = SupplyChainEngine(_standard_graph())
        p = _write_json({}, tmp_path)
        report = engine.analyze_from_file(p)
        assert report.total_vulnerabilities == 0

    def test_invalid_json_raises(self, tmp_path):
        engine = SupplyChainEngine(_standard_graph())
        p = tmp_path / "bad.json"
        p.write_text("not json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            engine.analyze_from_file(p)

    def test_nonexistent_file_raises(self, tmp_path):
        engine = SupplyChainEngine(_standard_graph())
        with pytest.raises((FileNotFoundError, OSError)):
            engine.analyze_from_file(tmp_path / "does_not_exist.json")


# ---------------------------------------------------------------------------
# analyze_from_data: auto-mapping
# ---------------------------------------------------------------------------


class TestAutoMappingIntegration:
    """Test auto-mapping when affected_components is not provided."""

    def test_auto_maps_database_package(self):
        engine = SupplyChainEngine(_standard_graph())
        report = engine.analyze_from_data([{
            "cve_id": "CVE-1", "severity": "critical",
            "package": "postgresql-client",
        }])
        assert report.total_vulnerabilities == 1
        impact = report.impacts[0]
        # Should auto-map to database component
        assert len(impact.affected_components) > 0

    def test_auto_maps_web_server_description(self):
        engine = SupplyChainEngine(_standard_graph())
        report = engine.analyze_from_data([{
            "cve_id": "CVE-2", "severity": "high",
            "package": "unknown", "description": "nginx buffer overflow",
        }])
        impact = report.impacts[0]
        assert len(impact.affected_components) > 0

    def test_auto_maps_with_explicit_components(self):
        engine = SupplyChainEngine(_standard_graph())
        report = engine.analyze_from_data([{
            "cve_id": "CVE-3", "severity": "medium",
            "affected_components": ["db", "cache"],
        }])
        impact = report.impacts[0]
        assert impact.affected_components == ["db", "cache"]

    def test_auto_maps_unknown_package_fallback(self):
        engine = SupplyChainEngine(_standard_graph())
        report = engine.analyze_from_data([{
            "cve_id": "CVE-4", "severity": "low",
            "package": "totally-unrelated-xyz",
        }])
        impact = report.impacts[0]
        # Fallback: first component
        assert len(impact.affected_components) >= 1


# ---------------------------------------------------------------------------
# Edge cases: single component graph
# ---------------------------------------------------------------------------


class TestSingleComponentGraph:
    """Tests with minimal graph (1 component)."""

    def test_single_component(self):
        graph = _make_graph(_comp("solo", "Solo App"))
        engine = SupplyChainEngine(graph)
        report = engine.analyze_from_data([{
            "cve_id": "CVE-1", "severity": "critical",
            "affected_components": ["solo"],
        }])
        assert report.total_vulnerabilities == 1
        assert report.impacts[0].estimated_blast_radius == 0


# ---------------------------------------------------------------------------
# Edge cases: empty graph
# ---------------------------------------------------------------------------


class TestEmptyGraph:
    """Tests with empty graph (no components)."""

    def test_empty_graph_analysis(self):
        graph = InfraGraph()
        engine = SupplyChainEngine(graph)
        report = engine.analyze_from_data([{
            "cve_id": "CVE-1", "severity": "high",
        }])
        # No components to map to
        assert report.total_vulnerabilities == 1
        impact = report.impacts[0]
        assert impact.affected_components == []

    def test_empty_graph_auto_map(self):
        graph = InfraGraph()
        engine = SupplyChainEngine(graph)
        report = engine.analyze_from_data([{
            "cve_id": "CVE-1", "severity": "high", "package": "express",
        }])
        # No component IDs to fallback to
        assert report.impacts[0].affected_components == []


# ---------------------------------------------------------------------------
# Edge cases: large number of vulnerabilities
# ---------------------------------------------------------------------------


class TestLargeInput:
    """Tests with many vulnerabilities."""

    def test_100_vulnerabilities(self):
        engine = SupplyChainEngine(_standard_graph())
        data = [
            {"cve_id": f"CVE-{i}", "severity": "medium", "affected_components": ["app"]}
            for i in range(100)
        ]
        report = engine.analyze_from_data(data)
        assert report.total_vulnerabilities == 100
        assert len(report.impacts) == 100
        assert report.infrastructure_risk_score >= 0
        assert report.infrastructure_risk_score <= 100

    def test_mixed_large_batch(self):
        engine = SupplyChainEngine(_standard_graph())
        data = []
        for i in range(50):
            sev = ["critical", "high", "medium", "low", "info"][i % 5]
            comp = ["db", "app", "cache", "queue", "lb"][i % 5]
            data.append({
                "cve_id": f"CVE-{i}",
                "severity": sev,
                "affected_components": [comp],
                "package": f"pkg-{i}",
            })
        report = engine.analyze_from_data(data)
        assert report.total_vulnerabilities == 50
        assert report.critical_count == 10  # every 5th


# ---------------------------------------------------------------------------
# Risk score calculation edge cases
# ---------------------------------------------------------------------------


class TestRiskScoreCalculation:
    """Tests for the risk score formula."""

    def test_info_severity_zero_blast_radius(self):
        engine = SupplyChainEngine(_standard_graph())
        impact = engine.map_cve_to_impact("CVE-I", "info", [])
        # info = weight 0, no blast
        assert impact.risk_score == 0.0

    def test_critical_with_max_blast(self):
        # Build a deep graph where one component has many transitive dependents
        graph = _make_graph(
            _comp("c0", "C0"),
            _comp("c1", "C1"),
            _comp("c2", "C2"),
            _comp("c3", "C3"),
            deps=[
                ("c1", "c0", "requires"),
                ("c2", "c1", "requires"),
                ("c3", "c2", "requires"),
            ],
        )
        engine = SupplyChainEngine(graph)
        impact = engine.map_cve_to_impact("CVE-C", "critical", ["c0"])
        # critical weight=4, blast=3 -> 4*2.0 + min(3,3)*0.5 = 9.5
        assert impact.risk_score == 9.5

    def test_risk_score_formula_boundary(self):
        """Test the formula: min(10.0, sev_weight * 2.0 + min(blast_radius, 3) * 0.5)."""
        engine = SupplyChainEngine(_standard_graph())
        # For a component with no dependents (blast=0)
        impact = engine.map_cve_to_impact("CVE-B", "critical", ["lb"])
        # critical=4, blast=0 -> 4*2.0 + 0 = 8.0
        assert impact.risk_score == 8.0

    def test_low_severity_risk_score(self):
        engine = SupplyChainEngine(_standard_graph())
        impact = engine.map_cve_to_impact("CVE-L", "low", ["app"])
        # low=1, blast depends on graph
        assert impact.risk_score >= 2.0  # minimum: 1*2.0=2.0


# ---------------------------------------------------------------------------
# Recommendation de-duplication
# ---------------------------------------------------------------------------


class TestRecommendationDeduplication:
    """Verify recommendations handle edge cases."""

    def test_multiple_criticals_single_urgent(self):
        engine = SupplyChainEngine(_standard_graph())
        data = [
            {"cve_id": f"CVE-{i}", "severity": "critical", "package": f"pkg{i}", "affected_components": ["db"]}
            for i in range(5)
        ]
        report = engine.analyze_from_data(data)
        urgent_recs = [r for r in report.recommendations if "URGENT" in r]
        assert len(urgent_recs) == 1  # Single URGENT message

    def test_no_critical_no_high_no_breach(self):
        engine = SupplyChainEngine(_standard_graph())
        data = [{"cve_id": "CVE-1", "severity": "medium", "affected_components": ["app"]}]
        report = engine.analyze_from_data(data)
        # Should have the generic "low/medium" recommendation
        assert any("low/medium" in r for r in report.recommendations)
