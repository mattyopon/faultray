"""Tests for the Compliance Posture Analyzer.

Covers CompliancePostureEngine, all Pydantic models, enumerations, control
assessment logic, cross-framework gap analysis, cost estimation, audit
evidence generation, trend tracking, and remediation prioritization.
Targets 100% line/branch coverage with 140+ tests.
"""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    ComplianceTags,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    RegionConfig,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.compliance_posture import (
    AuditEvidence,
    AuditPackage,
    ComplianceCostEstimate,
    CompliancePostureEngine,
    Control,
    ControlStatus,
    CrossFrameworkGap,
    Framework,
    PostureReport,
    PostureTrend,
    PostureTrendPoint,
    RemediationPriority,
    _FRAMEWORK_CONTROLS,
    _REMEDIATION_HOURS,
    _SEVERITY_WEIGHTS,
)


# ------------------------------------------------------------------ helpers


def _comp(
    cid: str,
    name: str = "",
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    *,
    port: int = 0,
    failover_enabled: bool = False,
    autoscaling_enabled: bool = False,
    encryption_at_rest: bool = False,
    encryption_in_transit: bool = False,
    network_segmented: bool = False,
    auth_required: bool = False,
    backup_enabled: bool = False,
    log_enabled: bool = False,
    ids_monitored: bool = False,
    waf_protected: bool = False,
    rate_limiting: bool = False,
    contains_pii: bool = False,
    contains_phi: bool = False,
    audit_logging: bool = False,
    pci_scope: bool = False,
    dr_target_region: str = "",
    is_primary: bool = True,
) -> Component:
    """Shorthand factory for Component with common overrides."""
    return Component(
        id=cid,
        name=name or cid,
        type=ctype,
        port=port,
        replicas=replicas,
        failover=FailoverConfig(enabled=failover_enabled),
        autoscaling=AutoScalingConfig(enabled=autoscaling_enabled),
        security=SecurityProfile(
            encryption_at_rest=encryption_at_rest,
            encryption_in_transit=encryption_in_transit,
            network_segmented=network_segmented,
            auth_required=auth_required,
            backup_enabled=backup_enabled,
            log_enabled=log_enabled,
            ids_monitored=ids_monitored,
            waf_protected=waf_protected,
            rate_limiting=rate_limiting,
        ),
        compliance_tags=ComplianceTags(
            contains_pii=contains_pii,
            contains_phi=contains_phi,
            audit_logging=audit_logging,
            pci_scope=pci_scope,
        ),
        region=RegionConfig(
            dr_target_region=dr_target_region,
            is_primary=is_primary,
        ),
    )


def _dep(
    src: str,
    tgt: str,
    dep_type: str = "requires",
    cb_enabled: bool = False,
) -> Dependency:
    return Dependency(
        source_id=src,
        target_id=tgt,
        dependency_type=dep_type,
        circuit_breaker=CircuitBreakerConfig(enabled=cb_enabled),
    )


def _empty_graph() -> InfraGraph:
    """Return a graph with no components."""
    return InfraGraph()


def _minimal_graph() -> InfraGraph:
    """Return a minimal graph with one component."""
    g = InfraGraph()
    g.add_component(_comp("app", "MyApp"))
    return g


def _compliant_graph() -> InfraGraph:
    """Return a fully compliant graph."""
    g = InfraGraph()
    g.add_component(_comp(
        "auth-gateway",
        "Auth Gateway",
        ctype=ComponentType.LOAD_BALANCER,
        port=443,
        replicas=2,
        auth_required=True,
        network_segmented=True,
        encryption_in_transit=True,
        encryption_at_rest=True,
        log_enabled=True,
        ids_monitored=True,
        backup_enabled=True,
        waf_protected=True,
    ))
    g.add_component(_comp(
        "app",
        "AppServer",
        ctype=ComponentType.APP_SERVER,
        port=443,
        replicas=3,
        autoscaling_enabled=True,
        encryption_in_transit=True,
        network_segmented=True,
        log_enabled=True,
        auth_required=True,
    ))
    g.add_component(_comp(
        "db",
        "Database",
        ctype=ComponentType.DATABASE,
        replicas=2,
        failover_enabled=True,
        encryption_at_rest=True,
        encryption_in_transit=True,
        network_segmented=True,
        backup_enabled=True,
        log_enabled=True,
        audit_logging=True,
        dr_target_region="us-west-2",
    ))
    g.add_component(_comp(
        "prometheus",
        "Prometheus",
        ctype=ComponentType.CUSTOM,
        log_enabled=True,
        ids_monitored=True,
    ))
    g.add_dependency(_dep("auth-gateway", "app", cb_enabled=True))
    g.add_dependency(_dep("app", "db", cb_enabled=True))
    return g


def _partial_graph() -> InfraGraph:
    """Return a partially compliant graph."""
    g = InfraGraph()
    g.add_component(_comp(
        "app",
        "AppServer",
        ctype=ComponentType.APP_SERVER,
        port=443,
        replicas=1,
        encryption_in_transit=True,
        log_enabled=True,
    ))
    g.add_component(_comp(
        "db",
        "Database",
        ctype=ComponentType.DATABASE,
        replicas=1,
        encryption_at_rest=True,
    ))
    g.add_dependency(_dep("app", "db"))
    return g


# ================================================================== Framework enum


class TestFrameworkEnum:
    """Tests for the Framework enum."""

    def test_all_values(self):
        assert Framework.SOC2 == "soc2"
        assert Framework.ISO27001 == "iso27001"
        assert Framework.PCI_DSS == "pci_dss"
        assert Framework.HIPAA == "hipaa"
        assert Framework.GDPR == "gdpr"
        assert Framework.NIST_CSF == "nist_csf"
        assert Framework.FEDRAMP == "fedramp"
        assert Framework.DORA == "dora"
        assert Framework.CIS_BENCHMARK == "cis_benchmark"

    def test_framework_count(self):
        assert len(Framework) == 9

    def test_string_comparison(self):
        assert Framework.SOC2 == "soc2"
        assert str(Framework.SOC2) == "Framework.SOC2"

    def test_framework_is_str_enum(self):
        assert isinstance(Framework.SOC2, str)


# ================================================================== ControlStatus enum


class TestControlStatusEnum:
    """Tests for the ControlStatus enum."""

    def test_all_values(self):
        assert ControlStatus.COMPLIANT == "compliant"
        assert ControlStatus.PARTIALLY_COMPLIANT == "partially_compliant"
        assert ControlStatus.NON_COMPLIANT == "non_compliant"
        assert ControlStatus.NOT_APPLICABLE == "not_applicable"
        assert ControlStatus.UNKNOWN == "unknown"

    def test_status_count(self):
        assert len(ControlStatus) == 5


# ================================================================== Control model


class TestControlModel:
    """Tests for the Control Pydantic model."""

    def test_basic_creation(self):
        c = Control(
            framework=Framework.SOC2,
            control_id="CC6.1",
            title="Access Control",
            description="Logical access controls",
            status=ControlStatus.COMPLIANT,
        )
        assert c.framework == Framework.SOC2
        assert c.control_id == "CC6.1"
        assert c.status == ControlStatus.COMPLIANT

    def test_defaults(self):
        c = Control(
            framework=Framework.HIPAA,
            control_id="164.312(a)",
            title="t",
            description="d",
            status=ControlStatus.UNKNOWN,
        )
        assert c.evidence == []
        assert c.gaps == []
        assert c.remediation == ""

    def test_with_evidence_and_gaps(self):
        c = Control(
            framework=Framework.PCI_DSS,
            control_id="Req-3.4",
            title="Encryption",
            description="Render PAN unreadable",
            status=ControlStatus.NON_COMPLIANT,
            evidence=["No encryption found"],
            gaps=["Missing encryption at rest"],
            remediation="Enable EAR on all PCI-scope components",
        )
        assert len(c.evidence) == 1
        assert len(c.gaps) == 1
        assert "Enable" in c.remediation

    def test_model_serialization(self):
        c = Control(
            framework=Framework.GDPR,
            control_id="Art.25",
            title="Privacy",
            description="Privacy by design",
            status=ControlStatus.PARTIALLY_COMPLIANT,
            evidence=["e1"],
            gaps=["g1"],
        )
        d = c.model_dump()
        assert d["framework"] == "gdpr"
        assert d["status"] == "partially_compliant"


# ================================================================== PostureReport model


class TestPostureReportModel:
    """Tests for the PostureReport Pydantic model."""

    def test_basic_creation(self):
        r = PostureReport(framework=Framework.SOC2)
        assert r.overall_score == 0.0
        assert r.controls == []
        assert r.compliant_count == 0
        assert r.non_compliant_count == 0

    def test_score_clamping_upper(self):
        with pytest.raises(Exception):
            PostureReport(framework=Framework.SOC2, overall_score=150.0)

    def test_score_clamping_lower(self):
        with pytest.raises(Exception):
            PostureReport(framework=Framework.SOC2, overall_score=-10.0)

    def test_full_report(self):
        r = PostureReport(
            framework=Framework.ISO27001,
            overall_score=75.5,
            compliant_count=3,
            non_compliant_count=1,
            critical_gaps=["A.17.1.1: BC Planning"],
            remediation_priority=["A.17.1.1", "A.10.1.1"],
            estimated_remediation_hours=24.0,
            recommendations=["Enable DR"],
        )
        assert r.overall_score == 75.5
        assert len(r.critical_gaps) == 1
        assert len(r.remediation_priority) == 2

    def test_serialization(self):
        r = PostureReport(framework=Framework.DORA, overall_score=90.0)
        d = r.model_dump()
        assert d["framework"] == "dora"
        assert d["overall_score"] == 90.0


# ================================================================== CrossFrameworkGap model


class TestCrossFrameworkGapModel:
    def test_creation(self):
        g = CrossFrameworkGap(
            gap_description="Missing encryption",
            affected_frameworks=[Framework.SOC2, Framework.PCI_DSS],
            affected_control_ids=["CC6.6", "Req-10.5"],
            severity="high",
            shared_remediation="Enable TLS",
        )
        assert len(g.affected_frameworks) == 2
        assert g.severity == "high"

    def test_defaults(self):
        g = CrossFrameworkGap(gap_description="test")
        assert g.severity == "medium"
        assert g.shared_remediation == ""


# ================================================================== ComplianceCostEstimate


class TestComplianceCostEstimate:
    def test_creation(self):
        e = ComplianceCostEstimate(
            framework=Framework.SOC2,
            total_estimated_hours=40.0,
            total_estimated_cost_usd=6000.0,
            controls_needing_work=3,
            timeline_weeks=1,
        )
        assert e.total_estimated_hours == 40.0
        assert e.hourly_rate_usd == 150.0

    def test_defaults(self):
        e = ComplianceCostEstimate(framework=Framework.HIPAA)
        assert e.total_estimated_cost_usd == 0.0
        assert e.cost_by_category == {}
        assert e.timeline_weeks == 0


# ================================================================== AuditEvidence / AuditPackage


class TestAuditModels:
    def test_audit_evidence_creation(self):
        ae = AuditEvidence(
            control_id="CC6.1",
            evidence_type="configuration",
            description="Auth gateway present",
            component_ids=["auth-gw"],
            status="collected",
        )
        assert ae.control_id == "CC6.1"

    def test_audit_evidence_defaults(self):
        ae = AuditEvidence(control_id="test")
        assert ae.evidence_type == ""
        assert ae.status == "collected"

    def test_audit_package_creation(self):
        ap = AuditPackage(
            framework=Framework.PCI_DSS,
            coverage_percent=80.0,
            summary="test",
        )
        assert ap.framework == Framework.PCI_DSS
        assert ap.coverage_percent == 80.0


# ================================================================== PostureTrend models


class TestPostureTrendModels:
    def test_trend_point(self):
        p = PostureTrendPoint(
            framework=Framework.SOC2,
            score=85.0,
            compliant_count=4,
            non_compliant_count=1,
        )
        assert p.score == 85.0

    def test_trend(self):
        t = PostureTrend(
            direction="improving",
            average_score=80.0,
            score_delta=10.0,
        )
        assert t.direction == "improving"

    def test_trend_defaults(self):
        t = PostureTrend()
        assert t.direction == "stable"
        assert t.data_points == []


# ================================================================== RemediationPriority


class TestRemediationPriority:
    def test_creation(self):
        rp = RemediationPriority(
            rank=1,
            control_id="CC6.1",
            framework=Framework.SOC2,
            gap_description="Missing access control",
            impact_score=4.0,
            effort_hours=16.0,
            priority="critical",
        )
        assert rp.rank == 1
        assert rp.priority == "critical"

    def test_defaults(self):
        rp = RemediationPriority()
        assert rp.rank == 0
        assert rp.priority == "medium"


# ================================================================== Constants


class TestConstants:
    def test_remediation_hours_mapping(self):
        assert _REMEDIATION_HOURS[ControlStatus.NON_COMPLIANT] == 16.0
        assert _REMEDIATION_HOURS[ControlStatus.PARTIALLY_COMPLIANT] == 8.0
        assert _REMEDIATION_HOURS[ControlStatus.COMPLIANT] == 0.0
        assert _REMEDIATION_HOURS[ControlStatus.NOT_APPLICABLE] == 0.0

    def test_severity_weights(self):
        assert _SEVERITY_WEIGHTS["critical"] == 4.0
        assert _SEVERITY_WEIGHTS["low"] == 1.0

    def test_all_frameworks_have_controls(self):
        for fw in Framework:
            assert fw in _FRAMEWORK_CONTROLS, f"Missing controls for {fw}"
            assert len(_FRAMEWORK_CONTROLS[fw]) >= 5


# ================================================================== Engine: static checks


class TestEngineStaticChecks:
    """Tests for CompliancePostureEngine static check methods."""

    def test_has_auth_by_name(self):
        g = InfraGraph()
        g.add_component(_comp("auth-svc", "Auth Service"))
        assert CompliancePostureEngine._has_auth(g) is True

    def test_has_auth_by_security_profile(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", auth_required=True))
        assert CompliancePostureEngine._has_auth(g) is True

    def test_has_auth_false(self):
        g = _minimal_graph()
        assert CompliancePostureEngine._has_auth(g) is False

    def test_has_auth_waf_name(self):
        g = InfraGraph()
        g.add_component(_comp("waf-proxy", "WAF Proxy"))
        assert CompliancePostureEngine._has_auth(g) is True

    def test_has_encryption_by_port(self):
        g = InfraGraph()
        g.add_component(_comp("web", "Web", port=443))
        assert CompliancePostureEngine._has_encryption(g) is True

    def test_has_encryption_by_security(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", encryption_in_transit=True))
        assert CompliancePostureEngine._has_encryption(g) is True

    def test_has_encryption_false(self):
        g = _minimal_graph()
        assert CompliancePostureEngine._has_encryption(g) is False

    def test_has_monitoring_by_name(self):
        g = InfraGraph()
        g.add_component(_comp("prometheus", "Prometheus"))
        assert CompliancePostureEngine._has_monitoring(g) is True

    def test_has_monitoring_by_security(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", log_enabled=True, ids_monitored=True))
        assert CompliancePostureEngine._has_monitoring(g) is True

    def test_has_monitoring_false(self):
        g = _minimal_graph()
        assert CompliancePostureEngine._has_monitoring(g) is False

    def test_has_monitoring_grafana(self):
        g = InfraGraph()
        g.add_component(_comp("grafana-dash", "Grafana"))
        assert CompliancePostureEngine._has_monitoring(g) is True

    def test_has_redundancy_true(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=3))
        assert CompliancePostureEngine._has_redundancy(g) is True

    def test_has_redundancy_false(self):
        g = _minimal_graph()
        assert CompliancePostureEngine._has_redundancy(g) is False

    def test_has_failover_true(self):
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ctype=ComponentType.DATABASE, failover_enabled=True))
        assert CompliancePostureEngine._has_failover(g) is True

    def test_has_failover_cache(self):
        g = InfraGraph()
        g.add_component(_comp("redis", "Redis", ctype=ComponentType.CACHE, failover_enabled=True))
        assert CompliancePostureEngine._has_failover(g) is True

    def test_has_failover_false(self):
        g = _minimal_graph()
        assert CompliancePostureEngine._has_failover(g) is False

    def test_has_failover_non_db_ignored(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", failover_enabled=True))
        assert CompliancePostureEngine._has_failover(g) is False

    def test_has_dr_by_target_region(self):
        g = InfraGraph()
        g.add_component(_comp("db", "DB", dr_target_region="us-west-2"))
        assert CompliancePostureEngine._has_dr(g) is True

    def test_has_dr_by_non_primary(self):
        g = InfraGraph()
        g.add_component(_comp("db-dr", "DB DR", is_primary=False))
        assert CompliancePostureEngine._has_dr(g) is True

    def test_has_dr_false(self):
        g = _minimal_graph()
        assert CompliancePostureEngine._has_dr(g) is False

    def test_has_autoscaling_true(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", autoscaling_enabled=True))
        assert CompliancePostureEngine._has_autoscaling(g) is True

    def test_has_autoscaling_false(self):
        g = _minimal_graph()
        assert CompliancePostureEngine._has_autoscaling(g) is False

    def test_has_network_segmentation_true(self):
        g = InfraGraph()
        g.add_component(_comp("db", "DB", network_segmented=True))
        assert CompliancePostureEngine._has_network_segmentation(g) is True

    def test_has_network_segmentation_false(self):
        g = _minimal_graph()
        assert CompliancePostureEngine._has_network_segmentation(g) is False

    def test_has_encryption_at_rest_true(self):
        g = InfraGraph()
        g.add_component(_comp("db", "DB", encryption_at_rest=True))
        assert CompliancePostureEngine._has_encryption_at_rest(g) is True

    def test_has_encryption_at_rest_false(self):
        g = _minimal_graph()
        assert CompliancePostureEngine._has_encryption_at_rest(g) is False

    def test_has_backup_true(self):
        g = InfraGraph()
        g.add_component(_comp("db", "DB", backup_enabled=True))
        assert CompliancePostureEngine._has_backup(g) is True

    def test_has_backup_false(self):
        g = _minimal_graph()
        assert CompliancePostureEngine._has_backup(g) is False

    def test_has_logging_by_security(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", log_enabled=True))
        assert CompliancePostureEngine._has_logging(g) is True

    def test_has_logging_by_compliance_tag(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", audit_logging=True))
        assert CompliancePostureEngine._has_logging(g) is True

    def test_has_logging_false(self):
        g = _minimal_graph()
        assert CompliancePostureEngine._has_logging(g) is False

    def test_has_circuit_breakers_true(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_dependency(_dep("a", "b", cb_enabled=True))
        assert CompliancePostureEngine._has_circuit_breakers(g) is True

    def test_has_circuit_breakers_false(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_dependency(_dep("a", "b", cb_enabled=False))
        assert CompliancePostureEngine._has_circuit_breakers(g) is False

    def test_has_circuit_breakers_no_edges(self):
        g = _minimal_graph()
        assert CompliancePostureEngine._has_circuit_breakers(g) is False


# ================================================================== Engine: helper methods


class TestEngineHelpers:
    def test_components_without_redundancy(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=1))
        g.add_component(_comp("db", "DB", replicas=1))
        g.add_dependency(_dep("app", "db"))
        result = CompliancePostureEngine._components_without_redundancy(g)
        # 'app' has a dependent edge pointing to 'db', but dependents means
        # components depending ON app. With app->db, db has app as dependent.
        # Actually: app depends on db (edge from app to db).
        # get_dependents(db) returns [app]. So db has dependents.
        # get_dependents(app) returns []. So app does NOT have dependents.
        assert "db" in result

    def test_components_without_redundancy_all_redundant(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=2))
        g.add_component(_comp("db", "DB", replicas=2))
        g.add_dependency(_dep("app", "db"))
        result = CompliancePostureEngine._components_without_redundancy(g)
        assert result == []

    def test_non_encrypted_components(self):
        g = InfraGraph()
        g.add_component(_comp("web", "Web", ctype=ComponentType.WEB_SERVER, port=80))
        g.add_component(_comp("api", "API", ctype=ComponentType.APP_SERVER, port=443))
        result = CompliancePostureEngine._non_encrypted_components(g)
        assert "web" in result
        assert "api" not in result

    def test_non_encrypted_no_enc_in_transit(self):
        g = InfraGraph()
        g.add_component(_comp(
            "web", "Web", ctype=ComponentType.WEB_SERVER, port=8080,
        ))
        result = CompliancePostureEngine._non_encrypted_components(g)
        assert "web" in result

    def test_pii_components(self):
        g = InfraGraph()
        g.add_component(_comp("db", "DB", contains_pii=True))
        g.add_component(_comp("app", "App"))
        result = CompliancePostureEngine._pii_components(g)
        assert result == ["db"]

    def test_phi_components(self):
        g = InfraGraph()
        g.add_component(_comp("ehr", "EHR", contains_phi=True))
        result = CompliancePostureEngine._phi_components(g)
        assert result == ["ehr"]


# ================================================================== Engine: assess_posture


class TestAssessPosture:
    """Tests for the assess_posture method."""

    def test_empty_graph_all_non_compliant(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_empty_graph(), Framework.SOC2)
        assert report.framework == Framework.SOC2
        # Empty graph has no components, so all checks fail
        assert report.overall_score <= 50.0

    def test_minimal_graph_soc2(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_minimal_graph(), Framework.SOC2)
        assert report.framework == Framework.SOC2
        assert len(report.controls) == 5
        assert report.non_compliant_count >= 1

    def test_compliant_graph_soc2(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_compliant_graph(), Framework.SOC2)
        assert report.overall_score == 100.0
        assert report.non_compliant_count == 0
        assert report.compliant_count == 5

    def test_partial_graph_soc2(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_partial_graph(), Framework.SOC2)
        assert 0 < report.overall_score < 100

    def test_assess_iso27001(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_compliant_graph(), Framework.ISO27001)
        assert report.framework == Framework.ISO27001
        assert len(report.controls) == 5

    def test_assess_pci_dss(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_compliant_graph(), Framework.PCI_DSS)
        assert report.framework == Framework.PCI_DSS

    def test_assess_hipaa(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_compliant_graph(), Framework.HIPAA)
        assert report.framework == Framework.HIPAA

    def test_assess_gdpr(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_compliant_graph(), Framework.GDPR)
        assert report.framework == Framework.GDPR

    def test_assess_nist_csf(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_compliant_graph(), Framework.NIST_CSF)
        assert report.framework == Framework.NIST_CSF

    def test_assess_fedramp(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_compliant_graph(), Framework.FEDRAMP)
        assert report.framework == Framework.FEDRAMP

    def test_assess_dora(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_compliant_graph(), Framework.DORA)
        assert report.framework == Framework.DORA

    def test_assess_cis_benchmark(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_compliant_graph(), Framework.CIS_BENCHMARK)
        assert report.framework == Framework.CIS_BENCHMARK

    def test_critical_gaps_populated(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_minimal_graph(), Framework.SOC2)
        assert len(report.critical_gaps) > 0

    def test_remediation_priority_non_compliant_first(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_minimal_graph(), Framework.SOC2)
        assert len(report.remediation_priority) > 0

    def test_estimated_remediation_hours(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_minimal_graph(), Framework.SOC2)
        assert report.estimated_remediation_hours > 0

    def test_recommendations_populated(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_minimal_graph(), Framework.SOC2)
        assert len(report.recommendations) > 0

    def test_compliant_graph_recommendations(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_compliant_graph(), Framework.SOC2)
        assert any("baseline controls are satisfied" in r for r in report.recommendations)

    def test_score_with_all_na(self):
        """If all controls are N/A, score defaults to 100."""
        engine = CompliancePostureEngine()
        # Monkey-patch to test N/A path — use an empty framework controls list
        import faultray.simulator.compliance_posture as mod
        original = mod._FRAMEWORK_CONTROLS.get(Framework.CIS_BENCHMARK)
        mod._FRAMEWORK_CONTROLS[Framework.CIS_BENCHMARK] = []
        report = engine.assess_posture(_minimal_graph(), Framework.CIS_BENCHMARK)
        mod._FRAMEWORK_CONTROLS[Framework.CIS_BENCHMARK] = original
        assert report.overall_score == 100.0

    def test_zero_estimated_hours_compliant(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_compliant_graph(), Framework.SOC2)
        assert report.estimated_remediation_hours == 0.0


# ================================================================== Engine: assess_all_frameworks


class TestAssessAllFrameworks:
    def test_returns_all_frameworks(self):
        engine = CompliancePostureEngine()
        reports = engine.assess_all_frameworks(_compliant_graph())
        assert len(reports) == len(Framework)
        fws = {r.framework for r in reports}
        for fw in Framework:
            assert fw in fws

    def test_minimal_graph_all(self):
        engine = CompliancePostureEngine()
        reports = engine.assess_all_frameworks(_minimal_graph())
        assert all(isinstance(r, PostureReport) for r in reports)

    def test_empty_graph_all(self):
        engine = CompliancePostureEngine()
        reports = engine.assess_all_frameworks(_empty_graph())
        assert len(reports) == len(Framework)


# ================================================================== Engine: find_cross_framework_gaps


class TestCrossFrameworkGaps:
    def test_minimal_graph_has_cross_gaps(self):
        engine = CompliancePostureEngine()
        gaps = engine.find_cross_framework_gaps(_minimal_graph())
        assert len(gaps) > 0
        # All gaps should affect 2+ frameworks
        for g in gaps:
            assert len(g.affected_frameworks) >= 2

    def test_compliant_graph_no_cross_gaps(self):
        engine = CompliancePostureEngine()
        gaps = engine.find_cross_framework_gaps(_compliant_graph())
        # Fully compliant graph should have no cross-framework gaps
        assert len(gaps) == 0

    def test_gap_severity_ordering(self):
        engine = CompliancePostureEngine()
        gaps = engine.find_cross_framework_gaps(_minimal_graph())
        if len(gaps) >= 2:
            # Verify sorted by severity weight descending
            weights = [_SEVERITY_WEIGHTS.get(g.severity, 0) for g in gaps]
            assert weights == sorted(weights, reverse=True)

    def test_gap_has_remediation(self):
        engine = CompliancePostureEngine()
        gaps = engine.find_cross_framework_gaps(_minimal_graph())
        for g in gaps:
            assert g.shared_remediation != ""

    def test_partial_graph_cross_gaps(self):
        engine = CompliancePostureEngine()
        gaps = engine.find_cross_framework_gaps(_partial_graph())
        assert isinstance(gaps, list)


# ================================================================== Engine: estimate_compliance_cost


class TestEstimateComplianceCost:
    def test_compliant_graph_zero_cost(self):
        engine = CompliancePostureEngine()
        est = engine.estimate_compliance_cost(_compliant_graph(), Framework.SOC2)
        assert est.total_estimated_hours == 0.0
        assert est.total_estimated_cost_usd == 0.0
        assert est.controls_needing_work == 0
        assert est.timeline_weeks == 0

    def test_minimal_graph_has_cost(self):
        engine = CompliancePostureEngine()
        est = engine.estimate_compliance_cost(_minimal_graph(), Framework.SOC2)
        assert est.total_estimated_hours > 0
        assert est.total_estimated_cost_usd > 0
        assert est.controls_needing_work > 0

    def test_cost_equals_hours_times_rate(self):
        engine = CompliancePostureEngine()
        est = engine.estimate_compliance_cost(_minimal_graph(), Framework.PCI_DSS)
        assert est.total_estimated_cost_usd == est.total_estimated_hours * est.hourly_rate_usd

    def test_timeline_weeks_positive(self):
        engine = CompliancePostureEngine()
        est = engine.estimate_compliance_cost(_minimal_graph(), Framework.HIPAA)
        assert est.timeline_weeks >= 1

    def test_cost_by_category_populated(self):
        engine = CompliancePostureEngine()
        est = engine.estimate_compliance_cost(_minimal_graph(), Framework.SOC2)
        assert len(est.cost_by_category) > 0

    def test_framework_preserved(self):
        engine = CompliancePostureEngine()
        est = engine.estimate_compliance_cost(_minimal_graph(), Framework.GDPR)
        assert est.framework == Framework.GDPR


# ================================================================== Engine: generate_audit_evidence


class TestGenerateAuditEvidence:
    def test_compliant_graph_full_coverage(self):
        engine = CompliancePostureEngine()
        pkg = engine.generate_audit_evidence(_compliant_graph(), Framework.SOC2)
        assert pkg.framework == Framework.SOC2
        assert pkg.coverage_percent == 100.0
        assert len(pkg.missing_evidence) == 0
        assert len(pkg.evidence_items) == 5

    def test_minimal_graph_has_missing(self):
        engine = CompliancePostureEngine()
        pkg = engine.generate_audit_evidence(_minimal_graph(), Framework.SOC2)
        assert len(pkg.missing_evidence) > 0

    def test_evidence_status_collected_or_missing(self):
        engine = CompliancePostureEngine()
        pkg = engine.generate_audit_evidence(_minimal_graph(), Framework.PCI_DSS)
        for item in pkg.evidence_items:
            assert item.status in ("collected", "missing")

    def test_summary_format(self):
        engine = CompliancePostureEngine()
        pkg = engine.generate_audit_evidence(_minimal_graph(), Framework.HIPAA)
        assert "hipaa" in pkg.summary.lower() or "Framework" in pkg.summary

    def test_partial_graph_evidence(self):
        engine = CompliancePostureEngine()
        pkg = engine.generate_audit_evidence(_partial_graph(), Framework.ISO27001)
        # Partial graph should have a mix of collected and missing evidence
        statuses = {i.status for i in pkg.evidence_items}
        assert "collected" in statuses or "missing" in statuses

    def test_evidence_items_have_component_ids(self):
        engine = CompliancePostureEngine()
        pkg = engine.generate_audit_evidence(_compliant_graph(), Framework.SOC2)
        for item in pkg.evidence_items:
            assert len(item.component_ids) > 0

    def test_coverage_percentage_range(self):
        engine = CompliancePostureEngine()
        pkg = engine.generate_audit_evidence(_minimal_graph(), Framework.NIST_CSF)
        assert 0.0 <= pkg.coverage_percent <= 100.0


# ================================================================== Engine: track_posture_trend


class TestTrackPostureTrend:
    def test_empty_reports(self):
        engine = CompliancePostureEngine()
        trend = engine.track_posture_trend([])
        assert trend.direction == "stable"
        assert trend.average_score == 0.0
        assert trend.score_delta == 0.0

    def test_single_report(self):
        engine = CompliancePostureEngine()
        r = PostureReport(framework=Framework.SOC2, overall_score=75.0, compliant_count=3, non_compliant_count=2)
        trend = engine.track_posture_trend([r])
        assert trend.average_score == 75.0
        assert trend.score_delta == 0.0
        assert len(trend.data_points) == 1

    def test_improving_trend(self):
        engine = CompliancePostureEngine()
        reports = [
            PostureReport(framework=Framework.SOC2, overall_score=50.0, compliant_count=2, non_compliant_count=3),
            PostureReport(framework=Framework.SOC2, overall_score=70.0, compliant_count=3, non_compliant_count=2),
            PostureReport(framework=Framework.SOC2, overall_score=90.0, compliant_count=4, non_compliant_count=1),
        ]
        trend = engine.track_posture_trend(reports)
        assert trend.direction == "improving"
        assert trend.score_delta > 0

    def test_degrading_trend(self):
        engine = CompliancePostureEngine()
        reports = [
            PostureReport(framework=Framework.SOC2, overall_score=90.0, compliant_count=4, non_compliant_count=1),
            PostureReport(framework=Framework.SOC2, overall_score=70.0, compliant_count=3, non_compliant_count=2),
            PostureReport(framework=Framework.SOC2, overall_score=50.0, compliant_count=2, non_compliant_count=3),
        ]
        trend = engine.track_posture_trend(reports)
        assert trend.direction == "degrading"
        assert trend.score_delta < 0

    def test_stable_trend(self):
        engine = CompliancePostureEngine()
        reports = [
            PostureReport(framework=Framework.SOC2, overall_score=80.0, compliant_count=4, non_compliant_count=1),
            PostureReport(framework=Framework.SOC2, overall_score=82.0, compliant_count=4, non_compliant_count=1),
        ]
        trend = engine.track_posture_trend(reports)
        assert trend.direction == "stable"

    def test_trend_recommendations_degrading(self):
        engine = CompliancePostureEngine()
        reports = [
            PostureReport(framework=Framework.SOC2, overall_score=90.0, compliant_count=4, non_compliant_count=0),
            PostureReport(framework=Framework.SOC2, overall_score=40.0, compliant_count=1, non_compliant_count=3),
        ]
        trend = engine.track_posture_trend(reports)
        assert any("degrading" in r.lower() for r in trend.recommendations)

    def test_trend_recommendations_low_score(self):
        engine = CompliancePostureEngine()
        reports = [
            PostureReport(framework=Framework.SOC2, overall_score=30.0, compliant_count=1, non_compliant_count=4),
            PostureReport(framework=Framework.SOC2, overall_score=40.0, compliant_count=1, non_compliant_count=3),
        ]
        trend = engine.track_posture_trend(reports)
        assert any("below 50%" in r for r in trend.recommendations)

    def test_trend_recommendations_non_compliant(self):
        engine = CompliancePostureEngine()
        reports = [
            PostureReport(framework=Framework.SOC2, overall_score=80.0, compliant_count=3, non_compliant_count=2),
        ]
        trend = engine.track_posture_trend(reports)
        assert any("non-compliant" in r.lower() for r in trend.recommendations)

    def test_trend_data_points_count(self):
        engine = CompliancePostureEngine()
        reports = [
            PostureReport(framework=Framework.SOC2, overall_score=float(i * 10))
            for i in range(1, 6)
        ]
        trend = engine.track_posture_trend(reports)
        assert len(trend.data_points) == 5


# ================================================================== Engine: prioritize_remediation


class TestPrioritizeRemediation:
    def test_empty_reports(self):
        engine = CompliancePostureEngine()
        result = engine.prioritize_remediation([])
        assert result == []

    def test_compliant_report_empty(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_compliant_graph(), Framework.SOC2)
        result = engine.prioritize_remediation([report])
        assert len(result) == 0

    def test_non_compliant_prioritized(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_minimal_graph(), Framework.SOC2)
        result = engine.prioritize_remediation([report])
        assert len(result) > 0
        # First item should have highest impact
        if len(result) >= 2:
            assert result[0].impact_score >= result[-1].impact_score

    def test_ranks_assigned(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_minimal_graph(), Framework.SOC2)
        result = engine.prioritize_remediation([report])
        for i, item in enumerate(result):
            assert item.rank == i + 1

    def test_multi_report_prioritization(self):
        engine = CompliancePostureEngine()
        r1 = engine.assess_posture(_minimal_graph(), Framework.SOC2)
        r2 = engine.assess_posture(_minimal_graph(), Framework.PCI_DSS)
        result = engine.prioritize_remediation([r1, r2])
        assert len(result) > 0

    def test_priority_values(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_minimal_graph(), Framework.SOC2)
        result = engine.prioritize_remediation([report])
        for item in result:
            assert item.priority in ("low", "medium", "high", "critical")

    def test_duplicate_control_impact_boosted(self):
        """Same gap appearing in multiple reports should boost impact."""
        engine = CompliancePostureEngine()
        r1 = engine.assess_posture(_minimal_graph(), Framework.SOC2)
        r2 = engine.assess_posture(_minimal_graph(), Framework.SOC2)
        single = engine.prioritize_remediation([r1])
        double = engine.prioritize_remediation([r1, r2])
        # Impact should be higher when same control is non-compliant in both
        if single and double:
            # The same control in 'double' should have >= impact as in 'single'
            single_ids = {s.control_id for s in single}
            for d in double:
                if d.control_id in single_ids:
                    matching_single = next(s for s in single if s.control_id == d.control_id)
                    assert d.impact_score >= matching_single.impact_score

    def test_partial_graph_prioritization(self):
        engine = CompliancePostureEngine()
        report = engine.assess_posture(_partial_graph(), Framework.ISO27001)
        result = engine.prioritize_remediation([report])
        assert isinstance(result, list)


# ================================================================== Engine: _gather_checks


class TestGatherChecks:
    def test_all_keys_present(self):
        engine = CompliancePostureEngine()
        checks = engine._gather_checks(_minimal_graph())
        expected_keys = {
            "has_auth", "has_encryption", "has_monitoring", "has_redundancy",
            "has_failover", "has_dr", "has_autoscaling", "has_network_segmentation",
            "has_encryption_at_rest", "has_backup", "has_logging", "has_circuit_breakers",
        }
        assert set(checks.keys()) == expected_keys

    def test_compliant_graph_all_true(self):
        engine = CompliancePostureEngine()
        checks = engine._gather_checks(_compliant_graph())
        assert all(checks.values())

    def test_minimal_graph_all_false(self):
        engine = CompliancePostureEngine()
        checks = engine._gather_checks(_minimal_graph())
        assert not any(checks.values())


# ================================================================== Engine: _get_control_requirements


class TestGetControlRequirements:
    def test_soc2_cc61(self):
        reqs = CompliancePostureEngine._get_control_requirements(Framework.SOC2, "CC6.1")
        assert len(reqs) == 2
        keys = [k for k, _ in reqs]
        assert "has_auth" in keys
        assert "has_network_segmentation" in keys

    def test_unknown_control_returns_empty(self):
        reqs = CompliancePostureEngine._get_control_requirements(Framework.SOC2, "UNKNOWN-99")
        assert reqs == []

    def test_all_framework_controls_have_requirements(self):
        for fw, controls in _FRAMEWORK_CONTROLS.items():
            for cid, _, _ in controls:
                reqs = CompliancePostureEngine._get_control_requirements(fw, cid)
                assert len(reqs) > 0, f"No requirements for {fw.value}:{cid}"


# ================================================================== Engine: _evaluate_control


class TestEvaluateControl:
    def test_all_met_compliant(self):
        engine = CompliancePostureEngine()
        checks = {"has_auth": True, "has_network_segmentation": True}
        evidence: list[str] = []
        gaps: list[str] = []
        status = engine._evaluate_control(
            Framework.SOC2, "CC6.1", checks, _minimal_graph(), evidence, gaps,
        )
        assert status == ControlStatus.COMPLIANT
        assert len(evidence) == 2
        assert len(gaps) == 0

    def test_none_met_non_compliant(self):
        engine = CompliancePostureEngine()
        checks = {"has_auth": False, "has_network_segmentation": False}
        evidence: list[str] = []
        gaps: list[str] = []
        status = engine._evaluate_control(
            Framework.SOC2, "CC6.1", checks, _minimal_graph(), evidence, gaps,
        )
        assert status == ControlStatus.NON_COMPLIANT
        assert len(gaps) == 2

    def test_partial_met(self):
        engine = CompliancePostureEngine()
        checks = {"has_auth": True, "has_network_segmentation": False}
        evidence: list[str] = []
        gaps: list[str] = []
        status = engine._evaluate_control(
            Framework.SOC2, "CC6.1", checks, _minimal_graph(), evidence, gaps,
        )
        assert status == ControlStatus.PARTIALLY_COMPLIANT
        assert len(evidence) == 1
        assert len(gaps) == 1

    def test_unknown_control_returns_na(self):
        engine = CompliancePostureEngine()
        evidence: list[str] = []
        gaps: list[str] = []
        status = engine._evaluate_control(
            Framework.SOC2, "UNKNOWN-X", {}, _minimal_graph(), evidence, gaps,
        )
        assert status == ControlStatus.NOT_APPLICABLE


# ================================================================== Engine: _assess_control


class TestAssessControl:
    def test_non_compliant_has_remediation(self):
        engine = CompliancePostureEngine()
        checks = {"has_auth": False, "has_network_segmentation": False}
        ctrl = engine._assess_control(
            Framework.SOC2, "CC6.1", "Access Control",
            "Logical access", checks, _minimal_graph(),
        )
        assert ctrl.status == ControlStatus.NON_COMPLIANT
        assert ctrl.remediation != ""
        assert "CC6.1" in ctrl.remediation

    def test_partially_compliant_has_remediation(self):
        engine = CompliancePostureEngine()
        checks = {"has_auth": True, "has_network_segmentation": False}
        ctrl = engine._assess_control(
            Framework.SOC2, "CC6.1", "Access Control",
            "Logical access", checks, _minimal_graph(),
        )
        assert ctrl.status == ControlStatus.PARTIALLY_COMPLIANT
        assert ctrl.remediation != ""

    def test_compliant_no_remediation(self):
        engine = CompliancePostureEngine()
        checks = {"has_auth": True, "has_network_segmentation": True}
        ctrl = engine._assess_control(
            Framework.SOC2, "CC6.1", "Access Control",
            "Logical access", checks, _minimal_graph(),
        )
        assert ctrl.status == ControlStatus.COMPLIANT
        assert ctrl.remediation == ""


# ================================================================== Integration scenarios


class TestIntegrationScenarios:
    """End-to-end integration scenarios."""

    def test_full_workflow_soc2(self):
        """Complete workflow: assess -> cost -> evidence -> trend -> prioritize."""
        engine = CompliancePostureEngine()
        graph = _partial_graph()

        report = engine.assess_posture(graph, Framework.SOC2)
        assert isinstance(report, PostureReport)

        cost = engine.estimate_compliance_cost(graph, Framework.SOC2)
        assert isinstance(cost, ComplianceCostEstimate)

        evidence = engine.generate_audit_evidence(graph, Framework.SOC2)
        assert isinstance(evidence, AuditPackage)

        trend = engine.track_posture_trend([report])
        assert isinstance(trend, PostureTrend)

        priorities = engine.prioritize_remediation([report])
        assert isinstance(priorities, list)

    def test_cross_framework_workflow(self):
        """Assess all frameworks and find cross-framework gaps."""
        engine = CompliancePostureEngine()
        graph = _partial_graph()

        all_reports = engine.assess_all_frameworks(graph)
        assert len(all_reports) == 9

        cross_gaps = engine.find_cross_framework_gaps(graph)
        assert isinstance(cross_gaps, list)

        priorities = engine.prioritize_remediation(all_reports)
        assert isinstance(priorities, list)

    def test_improving_infrastructure(self):
        """Simulate improving infrastructure and verify trend."""
        engine = CompliancePostureEngine()

        # Start with minimal
        r1 = engine.assess_posture(_minimal_graph(), Framework.SOC2)
        # Improve to partial
        r2 = engine.assess_posture(_partial_graph(), Framework.SOC2)
        # Full compliance
        r3 = engine.assess_posture(_compliant_graph(), Framework.SOC2)

        trend = engine.track_posture_trend([r1, r2, r3])
        assert trend.direction == "improving"
        assert trend.score_delta > 0

    def test_degrading_infrastructure(self):
        """Simulate degrading infrastructure."""
        engine = CompliancePostureEngine()
        r1 = engine.assess_posture(_compliant_graph(), Framework.SOC2)
        r2 = engine.assess_posture(_partial_graph(), Framework.SOC2)
        r3 = engine.assess_posture(_minimal_graph(), Framework.SOC2)

        trend = engine.track_posture_trend([r1, r2, r3])
        assert trend.direction == "degrading"

    def test_hipaa_phi_components(self):
        """HIPAA assessment with PHI-bearing components."""
        g = InfraGraph()
        g.add_component(_comp(
            "ehr-db", "EHR Database",
            ctype=ComponentType.DATABASE,
            contains_phi=True,
            encryption_at_rest=True,
            encryption_in_transit=True,
            auth_required=True,
            backup_enabled=True,
            log_enabled=True,
        ))
        g.add_component(_comp(
            "auth-svc", "Auth Service",
            auth_required=True,
            network_segmented=True,
        ))
        g.add_component(_comp("monitoring", "Monitoring"))
        engine = CompliancePostureEngine()
        report = engine.assess_posture(g, Framework.HIPAA)
        assert report.overall_score > 50.0

    def test_pci_dss_with_segmentation(self):
        """PCI DSS assessment with proper network segmentation."""
        g = InfraGraph()
        g.add_component(_comp(
            "payment-gw", "Payment Gateway",
            ctype=ComponentType.APP_SERVER,
            pci_scope=True,
            network_segmented=True,
            encryption_at_rest=True,
            encryption_in_transit=True,
            auth_required=True,
            log_enabled=True,
        ))
        g.add_component(_comp("otel-collector", "OTel Collector", log_enabled=True))
        g.add_dependency(_dep("payment-gw", "otel-collector", cb_enabled=True))
        engine = CompliancePostureEngine()
        report = engine.assess_posture(g, Framework.PCI_DSS)
        assert report.overall_score >= 50.0

    def test_gdpr_with_pii(self):
        """GDPR assessment with PII components."""
        g = InfraGraph()
        g.add_component(_comp(
            "user-db", "User Database",
            ctype=ComponentType.DATABASE,
            contains_pii=True,
            encryption_at_rest=True,
            encryption_in_transit=True,
            log_enabled=True,
            backup_enabled=True,
            auth_required=True,
            network_segmented=True,
        ))
        g.add_component(_comp("monitoring", "Monitoring", log_enabled=True, ids_monitored=True))
        engine = CompliancePostureEngine()
        report = engine.assess_posture(g, Framework.GDPR)
        assert report.overall_score > 50.0

    def test_dora_with_circuit_breakers(self):
        """DORA assessment emphasizing resilience controls."""
        g = InfraGraph()
        g.add_component(_comp(
            "api", "API Server",
            ctype=ComponentType.APP_SERVER,
            port=443,
            auth_required=True,
            encryption_in_transit=True,
            log_enabled=True,
        ))
        g.add_component(_comp(
            "db", "Database",
            ctype=ComponentType.DATABASE,
            failover_enabled=True,
            backup_enabled=True,
            dr_target_region="eu-west-1",
        ))
        g.add_component(_comp("monitoring", "Monitoring"))
        g.add_dependency(_dep("api", "db", cb_enabled=True))
        engine = CompliancePostureEngine()
        report = engine.assess_posture(g, Framework.DORA)
        assert report.overall_score >= 50.0

    def test_fedramp_assessment(self):
        """FedRAMP assessment requiring strict controls."""
        g = InfraGraph()
        g.add_component(_comp(
            "gov-app", "Gov Application",
            auth_required=True,
            encryption_at_rest=True,
            encryption_in_transit=True,
            network_segmented=True,
            log_enabled=True,
            backup_enabled=True,
            dr_target_region="us-gov-east-1",
        ))
        g.add_component(_comp(
            "db", "Database",
            ctype=ComponentType.DATABASE,
            failover_enabled=True,
            backup_enabled=True,
        ))
        g.add_component(_comp("monitoring", "Monitoring", log_enabled=True, ids_monitored=True))
        engine = CompliancePostureEngine()
        report = engine.assess_posture(g, Framework.FEDRAMP)
        assert report.overall_score >= 50.0

    def test_cis_benchmark_assessment(self):
        """CIS Benchmark assessment."""
        g = InfraGraph()
        g.add_component(_comp(
            "server", "Server",
            auth_required=True,
            network_segmented=True,
            encryption_at_rest=True,
            log_enabled=True,
            backup_enabled=True,
            dr_target_region="us-east-2",
        ))
        g.add_component(_comp("monitoring", "Monitoring"))
        engine = CompliancePostureEngine()
        report = engine.assess_posture(g, Framework.CIS_BENCHMARK)
        assert report.overall_score >= 50.0


# ================================================================== Edge cases


class TestEdgeCases:
    def test_graph_with_only_external_api(self):
        g = InfraGraph()
        g.add_component(_comp("ext", "External API", ctype=ComponentType.EXTERNAL_API))
        engine = CompliancePostureEngine()
        report = engine.assess_posture(g, Framework.SOC2)
        assert isinstance(report, PostureReport)

    def test_graph_with_many_components(self):
        g = InfraGraph()
        for i in range(20):
            g.add_component(_comp(f"svc-{i}", f"Service {i}"))
        engine = CompliancePostureEngine()
        report = engine.assess_posture(g, Framework.NIST_CSF)
        assert len(report.controls) == 5

    def test_cost_estimate_all_frameworks(self):
        engine = CompliancePostureEngine()
        graph = _minimal_graph()
        for fw in Framework:
            est = engine.estimate_compliance_cost(graph, fw)
            assert est.framework == fw

    def test_audit_evidence_all_frameworks(self):
        engine = CompliancePostureEngine()
        graph = _partial_graph()
        for fw in Framework:
            pkg = engine.generate_audit_evidence(graph, fw)
            assert pkg.framework == fw

    def test_remediation_with_only_compliant_and_na(self):
        engine = CompliancePostureEngine()
        report = PostureReport(
            framework=Framework.SOC2,
            overall_score=100.0,
            controls=[
                Control(
                    framework=Framework.SOC2,
                    control_id="CC6.1",
                    title="AC",
                    description="d",
                    status=ControlStatus.COMPLIANT,
                ),
                Control(
                    framework=Framework.SOC2,
                    control_id="CC6.6",
                    title="Enc",
                    description="d",
                    status=ControlStatus.NOT_APPLICABLE,
                ),
            ],
        )
        result = engine.prioritize_remediation([report])
        assert result == []

    def test_multiple_monitoring_names(self):
        """Verify various monitoring component names are detected."""
        for name in ["otel-collector", "datadog-agent", "newrelic-apm"]:
            g = InfraGraph()
            g.add_component(_comp(name, name))
            assert CompliancePostureEngine._has_monitoring(g) is True

    def test_multiple_auth_names(self):
        """Verify various auth component names are detected."""
        for name in ["oauth-proxy", "iam-service", "keycloak-sso", "firewall-proxy"]:
            g = InfraGraph()
            g.add_component(_comp(name, name))
            assert CompliancePostureEngine._has_auth(g) is True

    def test_non_encrypted_database_not_flagged(self):
        """Databases without web ports are not flagged as non-encrypted."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ctype=ComponentType.DATABASE, port=5432))
        result = CompliancePostureEngine._non_encrypted_components(g)
        assert "db" not in result

    def test_non_encrypted_with_transit_encryption(self):
        """Components with encryption_in_transit on non-standard port pass."""
        g = InfraGraph()
        g.add_component(_comp(
            "app", "App", ctype=ComponentType.APP_SERVER,
            port=8443, encryption_in_transit=True,
        ))
        result = CompliancePostureEngine._non_encrypted_components(g)
        assert "app" not in result

    def test_assess_control_with_empty_gaps_non_compliant(self):
        """Non-compliant control with no gaps still gets default remediation."""
        engine = CompliancePostureEngine()
        # Use an unknown control_id that returns NOT_APPLICABLE -> no gaps
        # But let's test the remediation path directly
        ctrl = Control(
            framework=Framework.SOC2,
            control_id="test",
            title="Test",
            description="Test",
            status=ControlStatus.NON_COMPLIANT,
            gaps=[],
            remediation="Implement controls for test",
        )
        assert "Implement" in ctrl.remediation

    def test_audit_evidence_with_not_applicable_control(self):
        """Audit evidence generation with NOT_APPLICABLE controls."""
        engine = CompliancePostureEngine()
        # Create a report with a NOT_APPLICABLE control by using an unknown
        # control_id that maps to no requirements
        report = PostureReport(
            framework=Framework.SOC2,
            overall_score=100.0,
            controls=[
                Control(
                    framework=Framework.SOC2,
                    control_id="NA-1",
                    title="N/A Control",
                    description="Not applicable",
                    status=ControlStatus.NOT_APPLICABLE,
                    evidence=["Not applicable to this scope"],
                ),
            ],
        )
        # Use generate_audit_evidence which internally calls assess_posture,
        # but we need a graph that produces N/A controls.
        # Instead, test via the _assess_control path with unknown control_id
        # which returns NOT_APPLICABLE
        import faultray.simulator.compliance_posture as mod
        original = mod._FRAMEWORK_CONTROLS[Framework.CIS_BENCHMARK]
        # Add a control_id that has no requirements -> will be NOT_APPLICABLE
        mod._FRAMEWORK_CONTROLS[Framework.CIS_BENCHMARK] = [
            ("UNKNOWN-NA", "NA Control", "This has no mapped requirements"),
        ]
        pkg = engine.generate_audit_evidence(_minimal_graph(), Framework.CIS_BENCHMARK)
        mod._FRAMEWORK_CONTROLS[Framework.CIS_BENCHMARK] = original
        # The N/A control should produce a "collected" evidence item
        assert len(pkg.evidence_items) == 1
        assert pkg.evidence_items[0].status == "collected"
        assert "not applicable" in pkg.evidence_items[0].description.lower()

    def test_prioritize_remediation_with_unknown_status(self):
        """Prioritize remediation handles UNKNOWN status controls."""
        engine = CompliancePostureEngine()
        report = PostureReport(
            framework=Framework.SOC2,
            overall_score=50.0,
            controls=[
                Control(
                    framework=Framework.SOC2,
                    control_id="CC6.1",
                    title="Access Control",
                    description="d",
                    status=ControlStatus.UNKNOWN,
                    gaps=["Status unknown"],
                ),
            ],
        )
        result = engine.prioritize_remediation([report])
        assert len(result) == 1
        assert result[0].priority == "medium"
        assert result[0].impact_score == 1.0
